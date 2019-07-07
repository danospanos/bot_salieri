from oandapyV20 import API
from oandapyV20.exceptions import V20Error
import oandapyV20.endpoints.instruments as instruments
import pandas as pd
import numpy as np
import requests
from bs4 import BeautifulSoup
import json
from itertools import product
import sys
from numpy import floor

class LoginError(Exception):
    pass


class BotSalieri:
    """Creates a bot which behaves as an average social networking trader (posts
    his current market view or trades) on fxmosphere website, can be extended to
    any website

    Attributes:
        oanda_api (dict): Contains API key and data specifications (pairs etc..)
        website (dict): Contains login credentials and URLs to request
        ma_length (int): Length of moving average period
        data (dict): Dict of currency pairs for which multiple time-frames are
            saved in DataFrames, how many of them depends on 'granularities'
        candidates (dict): Dict of candidates meeting tradable criterions
        decision (str): Best choice of results candidates, e.g. Buy USD_JPY
        post_message (str): Message to be posted as a status or blogpost
        balance_file (DataFrame): File with data to count total balance gain
    """

    ## TODO: Wrong evaluation when dicitonary of granularities is unordered !!!
    #TODO: is df passed by value or reference in _add_indicator_values??
    def __init__(self):
        with open('config.json', 'r') as config_file:
            config = json.load(config_file)
        self.oanda_api = config['oanda_api']
        self.website = config['website']
        self.ma_length = int(config['indicators']['ma_length'])
        self.data = config['oanda_api']['pairs']
        self.candidates = {}
        self.decision = 'Stay flat'
        self.post_message = 'I\'m sitting on my hands for this seance...'
        self.balance_data = self._total_balance_file()


    def get_data(self):
        """Download data from oandaV20 API for each currency pair and pass them
        to 'data' as DataFrames
        """
        for (key, value), g in product(
            self.data.items(), self.oanda_api['granularities']):
            self.oanda_api['data_params'].update({'granularity': g})
            r = instruments.InstrumentsCandles(
                instrument=key, params=self.oanda_api['data_params'])
            rd = API(access_token=self.oanda_api['token']).request(r)
            data = [rd['candles'][i]['mid']['c']
                for i in range(0, len(rd['candles']))]
            value.update({g: pd.DataFrame({'close':data})})


    def compute_indicators(self):
        """Update candle data with indicator values
        """
        for value, g in product(
            self.data.values(), self.oanda_api['granularities']):
            value[g] = self._add_indicator_values(value[g])


    def _add_indicator_values(self, df):
        """Calcualate indicator values, simple and weighted moving average

        args:
            df (DataFrame): Candle Data for one pair
            period (int): length of data to compute indicator from

        returns:
            updated df (DataFrame)
        """
        sum = np.sum([x for x in range(1,self.ma_length+1)])
        weights = [x/sum for x in range(1, self.ma_length+1)]
        df['ma'] = df['close'].rolling(self.ma_length).apply(np.mean, raw=True)
        df['wma'] = df['close'].rolling(self.ma_length).apply(
            lambda x: np.average(x, weights=weights), raw=True)
        return df


    def find_candidates(self):
        """Updates instance attribute candidates with tradable currency pairs
        """
        first_gran = self.oanda_api['granularities'][0]
        for key, value in self.data.items():
            last_close = float(value[first_gran]['close'].iloc[-1])
            last_ma = float(value[first_gran]['ma'].iloc[-1])
            gran_cntr = 0
            for g in self.oanda_api['granularities']:
                if value[g]['wma'].iloc[-1] > value[g]['ma'].iloc[-1]:
                    gran_cntr += 1
                if value[g]['wma'].iloc[-1] < value[g]['ma'].iloc[-1]:
                    gran_cntr -= 1
            #Buy side
            if gran_cntr == len(self.oanda_api['granularities']):
                pct_diff = last_close/last_ma - 1
                if pct_diff > 0:
                    self.candidates.update({key: pct_diff})
            #Sell side
            if gran_cntr == -1*len(self.oanda_api['granularities']):
                pct_diff = last_ma/last_close - 1
                if pct_diff > 0:
                    self.candidates.update({key: -1*pct_diff})


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
        return float(data[-1])


    def comment_prev_blogpost(self):
        """Compute the profit/loss on previous trading signal posted and post it
        to the blog_page
        """
        try:
            df = pd.read_csv('posts.csv')
            if df.empty:
                return
        except:
            return
        if 'JPY' in df.loc[0, 'pair']:
            multiplier = 100
        else:
            multiplier = 10000
        curr_price = self._ret_current_price(df.loc[0, 'pair'])
        if df.loc[0, 'dir'] == 'Buy':
            delta_pips = (curr_price - df.loc[0, 'price'])*multiplier
        elif df.loc[0, 'dir'] == 'Sell':
            delta_pips = (df.loc[0, 'price'] - curr_price)*multiplier
        if delta_pips >= 0:
            self.post_message = 'Total pips gained: ' + str(floor(delta_pips))
        else:
            self.post_message = 'Total pips lost:'  + str(floor(delta_pips))
        self._update_total_balance_file(delta_pips)
        mssg = '<br><br>Until today the overall {} was: '
        total_balance = self.balance_data.loc[0, 'balance']
        if total_balance >= 0:
            self.post_message += mssg.format('gain') + str(floor(total_balance))
        else:
            self.post_message += mssg.format('loss') + str(floor(total_balance))
        self.make_blogpost()
        #clear posts
        pd.DataFrame().to_csv('posts.csv')


    def _total_balance_file(self, filename='profit.csv'):
        """Profit counter file for purpose of profit counting over some time
        period

        args:
            filename (str): set by default. but can be changed for different
                bots

        returns:
            df (DataFrame): returns pandas DataFrame with data in it
        """
        ##TODO: add filename to config.json
        try:
            df = pd.read_csv(filename)
        except:
            df = pd.DataFrame({'balance':[0]})
            df.to_csv(filename)
        return df


    def _update_total_balance_file(self, delta_pips, filename='profit.csv'):
        """Update profit counter file for purpose of profit counting over some
        time period

        args:
            filename (str): set by default. but can be changed for different
                bots
        """
        ##TODO: add filename to config.json
        self.balance_data.loc[0, 'balance'] += delta_pips
        try:
            self.balance_data = self.balance_data.drop(columns=['Unnamed: 0'])
        except:
            pass
        self.balance_data.to_csv(filename)


    '''def create_table_to_post(self):
        """Create table witch all currency pairs defined in config.json, in this
        table all main time-frame are examined (its direction) and posted
        """
        PERIOD = 360'''


    def print_data(self, pair):
        for g in self.oanda_api['granularities']:
            print('Data granularity: ', g)
            print(self.data[pair][g].tail(3))


    def print_decision(self):
        print(self.decision)


    def print_message(self):
        print(self.post_message)


if __name__ == '__main__':
    salieri = BotSalieri()
    if sys.argv[1] == 'blogposter':
        salieri.get_data()
        salieri.compute_indicators()
        salieri.find_candidates()
        salieri.take_decision()
        salieri.create_message()
        salieri.save_post()
        salieri.make_blogpost()
    elif sys.argv[1] == 'profitcounter':
        salieri.comment_prev_blogpost()
    else:
        print('Wrong argument. Type \'blogposter\' or \'profitcounter\'.')
