#creating a python file defining contentful class and its classmethods to be imported into our main website app

import contentful
import logging
import os #allows drawing info from operative system
from dotenv import load_dotenv
#requires pip install python-dotenv
#loading information in .env file (e.g. secret keys)
load_dotenv()
 


class Contentful:
    client = contentful.Client(
        #the space id and the delivery token of the API key are drawn from the .env file
        os.getenv('CONTENTFUL_SPACE_ID'), 
        os.getenv('CONTENTFUL_DELIVERY_TOKEN')
        )


#    client = contentful.Client(
#        os.environ['CONTENTFUL_SPACE_ID'],
#        os.environ['CONTENTFUL_DELIVERY_TOKEN'])
    
#defining a method to get all the contentful entries whose content type is 'article'
    @classmethod
    def get_all_articles(cls):
        return cls.client.entries({
            'content_type': 'road-to-forest-valley-article' #note: the content type should be the content type ID on contenful 
        })

#defining a method to get all the contentful entries whose content type is 'article' and whose slug corresponds to input one
    @classmethod
    def get_article_by_slug(cls, slug):
        entries = cls.client.entries({
            'content_type': 'road-to-forest-valley-article',
            'fields.slug': slug
        })
        if entries:
            return entries[0]
        else:
            return None