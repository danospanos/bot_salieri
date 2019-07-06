# bot_salieri
Bot which behaves as social networking forex trader and posts his market view at forex trading social network.

It is capable of downloading external data from Oanda API, furthermore it decides what is the appropriate market condition to advise other traders with and finally comment under this client's blogpost which is sent via requests module.

# How to Use

It is advised, as specified by Pipfile, to use Python 3.6.0. For installing all required Python modules run `pipenv install`. 

Furthermore, `config.json.sample` file is included, you are required to fill in the login credentials as well as the Oanda's private API token. Fields such as currency pairs are free for any further edits.

With current release it is also possible to summarize current trading signals, however it has to be run before new `make_blogpost` function is invoked. For this purpose this bot runs under Cron, with `make_blogpost` is run in the morning and `comment_prev_blog` is run around midnight.
