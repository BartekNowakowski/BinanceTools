import pandas as pd
import numpy as np
from datetime import date
from parameters.params import Coins
from functions.misc import folder_check, gogogo, Color

pd.options.display.float_format = '{:.8f}'.format


def order_manager(client, portfolio, side, coin, pair, start, end, steps, part=None, amount=None, norm_dist=False,
                  show=True):

    if (part is not None) & (amount is not None):
        print('Please provide only one: part OR amount.')
        return

    if part is not None:
        if (part <= 0) | (part > 100):
            print(f'Part cannot be {part}. Please provide value 1-100')
            return

    if side == 'SELL':
        if part is None:
            balance = portfolio[(portfolio['account'] == 'Spot') & (portfolio['asset'] == coin)]['total'].reset_index(
                drop=True)[0]
            if amount > balance:
                print(f'Amount exceeds balance: {amount} > {balance}')
                return
        else:
            amount = portfolio[(portfolio['account'] == 'Spot') & (portfolio['asset'] == coin)]['total'].reset_index(
                drop=True)[0] * (part / 100)
    elif side == 'BUY':
        if amount is None:
            amount = portfolio[(portfolio['account'] == 'Spot') & (portfolio['asset'] == pair)]['free'].reset_index(
                drop=True)[0]
            if part is not None:
                amount *= (part / 100)
        else:
            amount = amount
    else:
        print(f'Wrong side: {side}\nShould be "BUY" or "SELL".')
        return

    orders = order_tailor(coin, side, norm_dist, start, end, steps, coins=amount)
    order_adjustment(client, orders, steps, norm_dist, start, end, amount, coin, pair, side, part, show)


def order_tailor(coin, side, norm_dist, start, end, steps, coins):
    prices = np.linspace(start, end, steps)

    if norm_dist:
        mean = np.mean(prices)
        sd = np.std(prices)
        prob_density = (np.pi * sd) * np.exp(-0.5 * ((prices - mean) / sd) ** 2)
    else:
        prob_density = [coins/steps] * steps

    df = pd.DataFrame(prob_density, columns=['distribution'])
    df = df.apply(lambda x: x/df['distribution'].sum())

    df['price'] = prices
    df['price'] = df['price'].apply(lambda x: round(x, Coins[coin]['price']))

    if side == 'SELL':
        df['coins'] = df['distribution'] * coins
        df['coins'] = df['coins'].apply(lambda x: round(x, Coins[coin]['lot']))
    else:
        df['coins'] = (df['distribution'] * coins) / df['price']
        df['coins'] = df['coins'].apply(lambda x: round(x, Coins[coin]['lot']))

    df['total_val'] = df['price'] * df['coins']
    df['total_val'] = df['total_val'].apply(lambda x: round(x, Coins[coin]['price']))
    df['distribution'] = df['distribution'].apply(lambda x: str(round(x * 100, 1)))

    return df[['distribution', 'price', 'coins', 'total_val']]


def order_adjustment(client, orders, steps, norm_dist, start, end, amount, coin, pair, side, part, show):
    if pair == 'USDT':
        min_val = 10
    elif pair == 'BTC':
        min_val = 0.0001
    else:
        print(f'{Color.RED}Only USDT and BTC have minimum value of an order specified. Please edit code: '
              f'def order_adjustment(){Color.END}')
        return

    if orders.total_val.min() < min_val:
        original = steps
        print(f'{"-"*69}\n'
              f'{Color.CYAN}Minimum value of an order has to be {Color.RED}{min_val} {pair}{Color.CYAN}.{Color.END}')

        min_notional = True
        while min_notional:
            steps -= 1
            orders = order_tailor(coin, side, norm_dist, start, end, steps, coins=amount)
            if orders.total_val.min() >= min_val:
                min_notional = False

        if(input(f'{"-"*69}\n'
                 f'{Color.CYAN}Number of steps have been reduced from '
                 f'{Color.RED}{original}{Color.CYAN} to: {Color.RED}{steps}{Color.CYAN}\n'
                 f'Do you want to proceed?\n'
                 f'{Color.GREEN}Y/N{Color.END} ? --> ').upper()) == 'Y':
            print_orders(orders, show)
            if gogogo(coin, pair, side, amount, start, end, steps) == 'Y':
                place_orders(client, orders, coin, pair, side, part)
    else:
        original = steps
        print(f'{"-" * 69}\n'
              f'{Color.CYAN}Minimum value of an order has to be {Color.RED}{min_val} {pair}{Color.CYAN}.{Color.END}')

        min_notional = True
        while min_notional:
            steps += 1
            orders = order_tailor(coin, side, norm_dist, start, end, steps, coins=amount)
            if orders.total_val.min() < min_val:
                steps -= 1
                orders = order_tailor(coin, side, norm_dist, start, end, steps, coins=amount)
                min_notional = False

        if (input(f'{"-" * 69}\n'
                  f'{Color.CYAN}Number of steps have been increased from '
                  f'{Color.RED}{original}{Color.CYAN} to: {Color.RED}{steps}{Color.CYAN}\n'
                  f'Do you want to proceed?\n'
                  f'{Color.GREEN}Y/N{Color.END} ? --> ').upper()) == 'Y':
            print_orders(orders, show)
            if gogogo(coin, pair, side, amount, start, end, steps) == 'Y':
                place_orders(client, orders, coin, pair, side, part)
        else:
            orders = order_tailor(coin, side, norm_dist, start, end, original, coins=amount)
            print_orders(orders, show)
            if gogogo(coin, pair, side, amount, start, end, original) == 'Y':
                place_orders(client, orders, coin, pair, side, part)


def print_orders(orders, show):
    if show:
        print(f'{"-"*69}')
        print(orders)


def place_orders(client, orders, coin, pair, side, part):
    last = len(orders) - 1

    for i, r in orders.iterrows():
        if part is not None:
            if (i == last) & (part == 100):
                quantity = round(float(client.get_asset_balance(asset=coin)['free']), Coins[coin]['lot'])
            else:
                quantity = r.coins
        else:
            quantity = r.coins

        post_order(client, coin=coin, pair=pair, quantity=quantity, price=r.price, side=side)


def post_order(client, coin, pair, quantity, price, side):
    client.create_order(
        symbol=coin + pair,
        side=side,
        type='LIMIT',
        timeInForce='GTC',
        quantity=quantity,
        price=price)
    print(f'LIMIT order: {side} {quantity} {coin} for {price} {pair}')


def get_orders(client, portfolio, save):
    print('Fetching all orders')

    order_types = {
        'symbol': object,
        'orderId': object,
        'orderListId': object,
        'clientOrderId': object,
        'price': float,
        'origQty': float,
        'executedQty': float,
        'cummulativeQuoteQty': float,
        'status': object,
        'timeInForce': object,
        'type': object,
        'side': object,
        'stopPrice': float,
        'icebergQty': float,
        'time': 'datetime64[ns]',
        'updateTime': 'datetime64[ns]',
        'isWorking': bool,
        'origQuoteOrderQty': float}

    df = pd.DataFrame()

    for coin in portfolio['asset']:
        try:
            df_coin = pd.DataFrame(client.get_all_orders(symbol=coin + 'USDT'))
            for col in ['time', 'updateTime']:
                df_coin[col] = pd.to_datetime(df_coin[col], unit='ms')

            df_coin = df_coin.astype(order_types)
            df_coin['p%'] = Coins[coin]['provision']
            df_coin['provision'] = np.where(df_coin.side == 'SELL',
                                            df_coin['p%'] * df_coin['cummulativeQuoteQty'],
                                            df_coin['p%'] * df_coin['executedQty'])
            del df_coin['p%']
            df = df.append(df_coin)

        except Exception as e:  # binance.exceptions.BinanceAPIException: APIError(code=-1121): Invalid symbol.
            if 'code=-1121' in str(e):
                pass

    if save is True:
        folder_check('orders')
        today = date.today().strftime('%Y-%m-%d')
        df.to_csv(f'orders/{today}_orders.csv', index=False)

    df.reset_index(drop=True, inplace=True)

    return df
