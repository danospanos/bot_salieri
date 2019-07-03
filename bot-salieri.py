from oandapyV20 import API
from oandapyV20.exceptions import V20Error
import oandapyV20.endpoints.instruments as instruments
import pandas as pd
import numpy as np
import requests
from bs4 import BeautifulSoup
import json
from itertools import product


class LoginError(Exception):
    pass


class BotSalieri:
    """Creates a bot which behaves as an average social networking trader (posts
    his current market view or trades) on fxmosphere website, can be extended to
    any website

    Attributes:
        oanda_api (dict): Contains API key and data specifications (pairs etc..)
        website (dict): Contains login credentials and URLs to request
        data_M15 (dict): Dict of DataFrames /w 15minute candles (for each pair)
        data_H4 (dict): Dict of DataFrames /w 4hour candles (for each pair)
        candidates (dict): Dict of candidates meeting tradable criterions
        decision (str): Best choice of results candidates, e.g. Buy USD_JPY
        post_message (str): Message to be posted as a status or blogpost
    """
    #TODO: is df passed by value or reference in _add_indicator_values??
    def __init__(self):
        with open('config.json', 'r') as config_file:
            config = json.load(config_file)
        self.oanda_api = config['oanda_api']
        self.website = config['website']
        self.data_M15 = {}
        self.data_H4 = {}
        self.candidates = {}
        self.decision = 'Stay flat'
        self.post_message = 'I\'m sitting on my hands for this seance...'


    def get_data(self):
        """Download data from oandaV20 API and pass them to data_M15 and data_H4
        as DataFrames
        """
        for g, p in product(self.oanda_api['granularities'],
                            self.oanda_api['pairs']):
            self.oanda_api['data_params'].update({'granularity': g})
            r = instruments.InstrumentsCandles(
                instrument=p, params=self.oanda_api['data_params'])
            rd = API(access_token=self.oanda_api['token']).request(r)
            data = [rd['candles'][i]['mid']['c']
                for i in range(0, len(rd['candles']))]
            if g == 'M15':
                self.data_M15.update({p: pd.DataFrame({'close':data})})
            else:
                self.data_H4.update({p: pd.DataFrame({'close':data})})


    def compute_indicators(self):
        """Update candle data with indicator values
        """
        for p in self.oanda_api['pairs']:
            self.data_M15[p] = self._add_indicator_values(self.data_M15[p], 360)
            self.data_H4[p] = self._add_indicator_values(self.data_H4[p], 270)


    def _add_indicator_values(self, df, period=360):
        """Calcualate indicator values, simple and weighted moving average

        args:
            df (DataFrame): Candle Data for one pair
            period (int): length of data to compute indicator from

        returns:
            updated df (DataFrame)
        """
        sum = np.sum([x for x in range(1,period+1)])
        weights = [x/sum for x in range(1, period+1)]
        df['ma'] = df['close'].rolling(period).apply(np.mean, raw=True)
        df['wma'] = df['close'].rolling(period).apply(
            lambda x: np.average(x, weights=weights), raw=True)
        return df


    def find_candidates(self):
        """Updates instance attribute candidates with tradable currency pairs
        """
        for p in self.oanda_api['pairs']:
            last_close = float(self.data_M15[p]['close'].iloc[-1])
            last_ma = float(self.data_M15[p]['ma'].iloc[-1])
            last_wma = float(self.data_M15[p]['wma'].iloc[-1])
            #Buy side
            if (self.data_H4[p]['wma'].iloc[-1] > self.data_H4[p]['ma'].iloc[-1]
                and last_wma > last_ma):
                pct_diff = last_close/last_ma - 1
                if pct_diff > 0:
                    self.candidates.update({p: pct_diff})
            #Sell side
            if (self.data_H4[p]['wma'].iloc[-1] < self.data_H4[p]['ma'].iloc[-1]
                and last_wma < last_ma):
                pct_diff = last_ma/last_close - 1
                if pct_diff > 0:
                    self.candidates.update({p: -1*pct_diff})


    def take_decision(self):
        """From self.candidates pick the best performing currency pair and
         update self.decision
        """
        if len(self.candidates) != 0:
            sort = sorted(self.candidates,
                          key= lambda x : abs(self.candidates[x]))
            first_key = list(sort)[0]
            if self.candidates[first_key] > 0:
                self.decision = 'Buy ' + first_key
            elif self.candidates[first_key] < 0:
                self.decision = 'Sell ' + first_key


    def create_message(self):
        """Creates message from messages.csv - file with message templates
        """
        if self.decision != 'Stay flat':
            df = pd.read_csv('messages.csv')
            mssg = df.sample()['message'].iloc[0]
            to_fill = self.decision.split(' ')
            self.post_message = mssg.format(to_fill[0], to_fill[1])


    def _login(self, blog_path, session):
        """Perform login under created session

        args:
            blog_path (str): Path to blog page
            session (class requests.Session):
        """
        login_url = self.website['signin_page'].format(blog_path.split('/')[0],
                                                       blog_path.split('/')[1])
        r = session.post(self.website['home_page'] + login_url,
                         data=self.website['login_credentials'])
        if r.reason != 'OK':
            raise LoginError('Login failed with status_code:'
                             + str(r.status_code))


    def make_statuspost(self):
        #TODO: after ning will solve issue with status posting
        #visit = 'http://www.forexmospherians.com/main/authorization/signIn?target=http%3A%2F%2Fwww.forexmospherians.com%2Fforexmosphere-community-home'
        pass


    def make_blogpost(self, blog_path='market-alerts/my-trading-journal'):
        """Send POST request with generated message

        args:
            blog_path (str): Path to blog page on which to make blogpost
        """
        with requests.Session() as s:
            self._login(blog_path, s)
            r = s.get(self.website['home_page'] + blog_path)
            soup = BeautifulSoup(r.text, 'html.parser')
            xg_token = soup.find('input', {'name':'xg_token'})['value']
            self.website['pass_data'].update({
                'xg_token': xg_token,
                'commentText': '<p>' + self.post_message + '</p>'
                })
            r = s.post(
                self.website['home_page'] + self.website['request_page'],
                data=self.website['pass_data'])


    def save_post(self):
        """Each post made is saved to posts.csv
        """
        #if false, there was nothing to save
        if self.decision != 'Stay flat':
            try:
                df = pd.read_csv('posts.csv')
            except:
                df = pd.DataFrame()
            dec = self.decision.split(' ')
            price = self._ret_current_price(dec[1])
            df = df.append({
                'pair': dec[1],
                'dir':dec[0],
                'price':price
                }, ignore_index=True)
            df.to_csv('posts.csv')


    def _ret_current_price(self, instrument):
        """Fetch current data for instrument from oandaV20 API

        args:
            instrument (str): instrument format recognized by oanda (eg GBP_USD)

        returns:
            current_price (float)
        """
        params = {'price':'M', 'count':'3', 'granularity': 'M1'}
        r = instruments.InstrumentsCandles(instrument=instrument, params=params)
        rd = API(access_token=self.oanda_api['token']).request(r)
        data = [rd['candles'][i]['mid']['c']
            for i in range(0, len(rd['candles']))]
        return data[-1]


    def print_data(self, pair):
        print(self.data_M15[pair].tail(3))
        print(self.data_H4[pair].tail(3))


    def print_decision(self):
        print(self.decision)


    def print_message(self):
        print(self.post_message)


if __name__ == '__main__':
    salieri = BotSalieri()
    salieri.get_data()
    salieri.compute_indicators()
    salieri.find_candidates()
    salieri.take_decision()
    salieri.create_message()
    salieri.make_blogpost()
