# -*- coding: utf-8 -*-

# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://doc.scrapy.org/en/latest/topics/item-pipeline.html
import re
from datetime import datetime
from decimal import Decimal

from auctions.models import Auction, City, SalesHistory, AuctionImage


class ScrapyAppPipeline(object):

    def process_item(self, item, spider):
        city, created = City.objects.get_or_create(city=item['city'], prov=item['prov'])

        auction = {
            'lot_id': 'idLotto',
            'auction_code': 'code',
            'category': 'idTipologia',
            'address': 'address',
            'latitude': 'latitudine',
            'longitude': 'longitudine',
            'price': 'price',
            'min_offer': 'min_offer',
        }
        for key, value in auction.items():
            if value not in item:
                raise Exception("Can't find '" + value + "' field")
            else:
                value = item[value]

            if key in ('latitude', 'longitude'):
                value = Decimal(value)
            elif key in ('lot_id', 'auction_code', 'category', 'price', 'min_offer'):
                value = self.extract_number(value)
            auction[key] = value

        auction['city'] = city
        auction['data'] = item
        auction['last_crawling'] = datetime.now()

        db_auction, created = Auction.objects.update_or_create(auction_code=auction['auction_code'], defaults=auction)

        # images
        attachments = item['Attachments']

        attachments_iter = {
            'pictures': AuctionImage.IMAGE,
            'plants': AuctionImage.PLANT
        }

        for img_category, img_type in attachments_iter.iteritems():
            if img_category in attachments:
                for pic, path in attachments[img_category].iteritems():
                    AuctionImage.objects.update_or_create(auction=db_auction, image=path, image_type=img_type,
                                                          title=pic)

        for old_auction in item['old_auctions']:
            auction_date = datetime.strptime(old_auction['dataVendita'], '%Y-%m-%dT%H:%M:%S')
            old_auction_data = {
                'date': auction_date,
                'sale_type': old_auction['tipoVendita'],
                'price': Decimal(old_auction['prezzoBase']),
                'auction': db_auction
            }
            if created:
                SalesHistory.objects.create(old_auction_data)
            else:
                SalesHistory.objects.get_or_create(date=auction_date, auction=db_auction, defaults=old_auction_data)
		
		return item

    @staticmethod
    def extract_number(value_str):
        value = None
        if value_str:
            num_re = re.search(r'(?P<value>[1-9][0-9.]*(?P<decimal>,[0-9]+)?)$', value_str)
            if num_re:
                value = num_re.group('value').replace('.', '').replace(',', '.')
                if num_re.group('decimal'):
                    value = Decimal(value)
                else:
                    value = int(value)
        return value
