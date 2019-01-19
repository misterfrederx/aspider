# -*- coding: utf-8 -*-
import errno
import json
import os
import re

import scrapy
import xmltodict
from scrapy import Selector
from scrapy.http import Request


class AsteSpider(scrapy.Spider):
    MEDIA_PATH = '../media'
    BASE_URL = 'https://www.********.**/'
    WEB_API = 'https://webapi.********.**/api/'
    IGNORE_EMPTY = True
    name = 'aste'
    allowed_domains = ['********.**']

    def __init__(self, **kwargs):
        super(AsteSpider, self).__init__()
        crawling_codes = kwargs['crawling_codes']
        self.crawling_codes = crawling_codes.split(',') if crawling_codes else None
        self.logger.info("************************* INIT *************************")
        self.logger.debug(self.crawling_codes)

    # def error_bin(self, failure):
    #     if hasattr(failure.value, 'response'):
    #         response = failure.value.response

    def start_requests(self):

        if not self.crawling_codes:
            raise Exception('Nothing to crawl!')

        search_url = self.WEB_API + '/search/map'
        headers = {
            'Content-Type': 'application/json'
        }
        body = {
            'codiceAsta': None,
            'latitudineNE': None,
            'latitudineNW': None,
            'latitudineSE': None,
            'latitudineSW': None,
            'longitudineNE': None,
            'longitudineNW': None,
            'longitudineSE': None,
            'longitudineSW': None,
            'tipoRicerca': '1',
            "idTipologie": [1, 2, 3, 4, 5],
            "idCategorie": [],
            'comune': None,
            'provincia': None,
            'prezzoDa': '0',
            'orderBy': '1',
        }
        requests = []
        for sys_id in self.crawling_codes:
            self.logger.info('Start crawling id %s', sys_id)
            body['codiceAsta'] = sys_id
            requests.append(scrapy.http.Request(search_url, method='POST', headers=headers, body=json.dumps(body),
                                                callback=self.parse))  # , errback=self.error_bin)]
        return requests

    def parse(self, response):
        xml_string = response.body
        results = xmltodict.parse(xml_string)

        if 'ArrayOfMapSearchResult' not in results:
            raise Exception('Cannot find results bin')

        if 'MapSearchResult' not in results['ArrayOfMapSearchResult']:
            raise Exception('No results!')

        results = AsteSpider.listify(results['ArrayOfMapSearchResult']['MapSearchResult'])

        for result in results:
            detail_url = self.BASE_URL + 'vendita-asta-dettaglio-' + result['idLotto']
            yield Request(detail_url, callback=self.parse_detail, meta=result)  #, errback=self.error_bin)
            
    def parse_detail(self, response):
        sel = Selector(response)
        data = response.meta
        sys_id = data['idLotto']

        title_row = sel.xpath("//div[@id='titlebar']").css(".row")
        code = AsteSpider.read(title_row.css(".title-bar-auction-left").re('\d+'))
        AsteSpider.add(data, 'code', code, allow_empty=True)

        AsteSpider.add(data, 'status', title_row.css(".title-bar-auction-right").xpath("./text()"))
        AsteSpider.add(data, 'semaphore', title_row.re("auction-check-([a-z]+)"))
        AsteSpider.add(data, 'price', title_row.css(".property-pricing").xpath(".//span/following-sibling::text()"),
                       allow_empty=True)
        AsteSpider.add(data, 'min_offer', title_row.css(".sub-price").re(".{1}\s[0-9\.]+,\d+"), allow_empty=True)

        # Sell's data
        section = {}
        for div in sel.css(".widget").css(".row").xpath("./div"):
            AsteSpider.div_pair(div, section)
        header = AsteSpider.read(sel.css('.widget').xpath("./h3/text()"))
        data[header] = section

        custodian_phone = AsteSpider.read(sel.css(".js-custode").xpath("./@href[starts-with(., 'tel')]").re(r"\+?\d+"))
        AsteSpider.add(data, 'custodian_phone', custodian_phone)

        # Attachments
        attachments = {}
        for media_type in ('pictures', 'plants'):
            xpath = "//div[@id='%s']//a" % media_type
            media_dic = {}
            for a in sel.xpath(xpath):
                file_name = AsteSpider.read(a.xpath("./@title"))
                href = AsteSpider.read(a.xpath("./@href"))
                img_path = '/'.join([code, media_type, file_name])
                meta = {'output_path': self.MEDIA_PATH + '/' + img_path}
                yield response.follow(url=href, callback=self.parse_attachment, meta=meta)
                AsteSpider.add(media_dic, file_name, img_path)
            attachments[media_type] = media_dic

        for a in sel.css(".rowFiles").xpath("./div/a"):
            href = AsteSpider.read(a.xpath("./@href"))
            header = AsteSpider.read(a.xpath("./*/following-sibling::text()"))
            AsteSpider.add(attachments, header, href)
        if len(attachments) > 0:
            data['Attachments'] = attachments

        # Main features
        property_description = sel.css('.property-description')
        if len(property_description) <= 0:
            raise Exception('Main div not found')
        property_description = property_description[0]

        # Details
        good_detail = property_description.css('.good-detail')
        AsteSpider.add(data, 'title', good_detail.xpath('./h4/text()'))
        AsteSpider.add(data, 'full_address', good_detail.xpath('./div/a/@title'))
        AsteSpider.add(data, 'description', good_detail.xpath('./p/text()'))

        # Extract city and prov
        address = good_detail.xpath(
            "(//div[contains(@class,'detail-feature')])[1]/a/following-sibling::text()[1]").extract()
        AsteSpider.add(data, 'address', AsteSpider.sanitize(address[0]))
        city_prov = re.search(r'(?P<city>.+)\((?P<prov>[A-Z]{2})\)$', AsteSpider.sanitize(address[1]))
        if city_prov:
            for key in ('city', 'prov'):
                AsteSpider.add(data, key, city_prov.group(key))
        else:
            raise Exception('city/prov parsing error')

        details = {}
        for div in good_detail.xpath(".//div[@class='row']/div[count(div)=2]"):
            AsteSpider.div_pair(div, details)
        if len(details) > 0:
            data['Details'] = details

        # Features
        header = None
        for element in property_description.xpath(".//div[contains(@class,'legal-row-desc')]/*[self::h3 or self::div]"):
            find_header = AsteSpider.read(element.css(".desc-headline").xpath("./text()"))
            if find_header:
                header = find_header
            else:
                section = {}
                for div in element.xpath('div[count(div)=2]'):
                    AsteSpider.div_pair(div, section)
                if len(section) > 0:
                    data[header] = section

        # Old auctions
        old_auctions_url = self.WEB_API + "VenditePrecedenti/{id}/{code}".format(id=sys_id, code=code)
        yield Request(url=old_auctions_url, callback=self.parse_old_auctions, meta=data,
                      priority=1)  #, errback=self.error_bin)

    def parse_attachment(self, response):
        output_path = response.meta['output_path']
        AsteSpider.check_dir(output_path)
        with open(output_path, "w") as f:
            f.write(response.body)

    def parse_old_auctions(self, response):
        xml_string = response.body
        old_auctions_dict = xmltodict.parse(xml_string)
        data = response.meta
        data['old_auctions'] = AsteSpider.listify(old_auctions_dict['ArrayOfVenditaPrecedente']['VenditaPrecedente'])
        yield data

    @staticmethod
    def div_pair(div, data):
        key = AsteSpider.read(div.xpath('div[1]/text()'))
        value = AsteSpider.read(div.xpath('div[2]/text()'))
        AsteSpider.add(data, key, value)

    @staticmethod
    def add(data, key, value, allow_empty=False):
        value = AsteSpider.read(value)
        if allow_empty or not AsteSpider.IGNORE_EMPTY or (value and value != '-'):
            data[key] = value if value != '-' else None

    @staticmethod
    def read(element):
        if type(element) == scrapy.selector.unified.SelectorList:
            value = AsteSpider.sanitize(element.extract_first())
        elif type(element) == list and len(element) > 0:
            value = element[0]
        else:
            value = element
        return value

    @staticmethod
    def sanitize(lines, separator=' '):
        value = None
        if lines:
            lines = lines.encode('utf-8')
            values = []
            for line in lines.splitlines():
                line = line.strip(' /\n/\r/\t')
                if len(line) > 0:
                    values.append(line)
            value = separator.join(values)
        return value

    @staticmethod
    def check_dir(file_path):
        dir_path = os.path.dirname(file_path)
        if not os.path.exists(dir_path):
            try:
                os.makedirs(dir_path)
            except OSError as exc:  # Guard against race condition
                if exc.errno != errno.EEXIST:
                    raise

    @staticmethod
    def listify(item):
        if type(item) is not list:
            item = [item]
        return item
