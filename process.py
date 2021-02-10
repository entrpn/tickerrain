import math

import asyncio

import redis

import pprint
import time
import functools

import numpy as np

from datetime import datetime
from dateutil import tz
import datetime

import news
import spacy

from spacy import displacy

import nltk
import pandas as pd
import re

import spacy
import nltk
nltk.download('vader')
nltk.download('vader_lexicon')

from nltk.sentiment.vader import SentimentIntensityAnalyzer

from spacy import displacy

import asyncio

import cachetools.func


r = redis.Redis(
host='localhost',
port=6379,)

r = redis.Redis(db=8)


processed_posts = []

last_process_idx = 5


def get_last_process():
    global last_process_idx

    last = r.lrange("last10keys", 0, 9)[last_process_idx]
    post = r.hgetall(last)

    last_process_idx = (last_process_idx + 1) % 10

    p_type = 'submission'
    tickers_ment = str(post[b'tickers_ment'].decode("utf-8"))
    process_body = str(post[b'process_body'])

    p_title = None
    p_score = None
    p_body = None

    if(b'comment_body' in post):
        p_type = "comment"
        p_body = str(post[b'comment_body'].decode("utf-8"))
        p_score = str(post[b'comment_score'])
    else:
        p_title = str(post[b'title'])
        p_score = str(post[b'score'])
        p_body = str(post[b'body'].decode("utf-8"))


    return {"type":p_type,
            'title': p_title,
            'body':p_body,
            'process_body':process_body,
            'tickers_ment':tickers_ment,
            'score':p_score,
            }


def create_pandas():
    data_all = []
    cursor = 0
    while(True):
        cursor, posts_ret = r.scan(cursor, "submi:*", 100)
        for post in posts_ret:
            post_content = r.hgetall(post)

            post_id = post
            post_score = post_content[b'score'].decode("utf-8")
            post_body = post_content[b'body'].decode("utf-8")
            post_title = post_content[b'title'].decode("utf-8") + " " + post_body
            post_created = post_content[b'created'].decode("utf-8")

            data_all.append([post_id, post_score, post_body, post_title, post_created])


        if(cursor == 0):
            break

    df = pd.DataFrame(data_all, columns=['id', 'score', 'body', 'title', 'created']) 
    return df





def process_tickers(text):
    tickers_ment = set([word.split("$")[-1] for word in text.split() if word.startswith('$')])

    text = re.sub('[^a-zA-Z0-9 \n\.]', ' ', text)
    text = [' '.join(filter(str.isupper, word.split())) for word in text.split()]
    #tickers_ment = list(set([word for word in text.split(" ")]).intersection(set(tickers)))
    tickers_ment = tickers_ment.union(set([word for word in text]))

    tickers_ment = tickers_ment.intersection(set(news.tickers))

    list_tickers = [ticker.upper() for ticker in tickers_ment] 

    return list_tickers

    


nlp = spacy.load("en_core_web_lg")

def sentiment(row, ret_doc=False):
    tickers_ment = row['tickers']

    if(len(tickers_ment) == 0):
        return None, None

    sentence = row['body'].strip()

    tk_spans = []

    doc = nlp(sentence)

    sid = SentimentIntensityAnalyzer()
    sentiment = sid.polarity_scores(doc.text)

    if(len(tickers_ment) > 1):
        for ticker in tickers_ment:
            pos = doc.text.find(ticker)
            #tk_spans.append(doc.char_span(pos, pos + len(ticker), label="ORG"))
            span = doc.char_span(pos, pos + len(ticker), label="ORG")
            #import pudb; pudb.set_trace()
            #print(f"ticker : {ticker} and tickerment {tickers_ment}, span {span}")          
            try:
                doc.ents = [span if e.text == ticker else e for e in doc.ents]
            except Exception as e:
                print(e)

    print('Processed another one')


    if(ret_doc == False):
        return doc.ents, sentiment
    else:
        return doc, sentiment

def calculate_df(df):
    data_df = df.filter(['tickers', 'score', 'sentiment'])

    tickers_processed = pd.DataFrame(df.tickers.explode().value_counts())

    tickers_processed = tickers_processed.rename(columns = {'tickers':'counts'})

    tickers_processed['score'] = 0.0
    tickers_processed['sentiment'] = 0.0

    for idx, row_tick in enumerate(tickers_processed.iloc):
        for row_data in data_df.iloc:
            if(row_tick.name in row_data.tickers):
     
                row_tick['sentiment'] += row_data.sentiment['compound'] / row_tick.counts
                row_tick['score'] += int(row_data.score) / row_tick.counts
                tickers_processed.iloc[idx] = row_tick

    return tickers_processed

def day3_filter(row):
    now = time.time()
    if(now - float(row['created']) < 3*86_400):
        return True
    else:
        return False


def day_filter(row):
    now = time.time()
    if(now - float(row['created']) < 86_400):
        return True
    else:
        return False


#@cachetools.func.ttl_cache(maxsize=128, ttl=75)
def processed_df():
    df = create_pandas()
    df['tickers'] = df.apply(lambda row: process_tickers(row.body), axis=1)
    
    df["ents"], df["sentiment"] = zip(*df.apply(sentiment, axis=1))

    df_3, df_1 = df[df.apply(day3_filter, axis=1)], df[df.apply(day_filter, axis=1)]

    return calculate_df(df), calculate_df(df_3), calculate_df(df_1)


async def processing_last():
    while True:
        await asyncio.sleep(120)
        last_processed, last_processed_3, last_processed_1 = processed_df()
        last_processed.to_pickle('tickers_df_7.p')
        last_processed_3.to_pickle('tickers_df_3.p')
        last_processed_1.to_pickle('tickers_df_1.p')
        print('Finished Processing awaiting 120secs')
        


if __name__ == '__main__':

    asyncio.run(processing_last())
