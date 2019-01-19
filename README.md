# aspider

This is an extract of a project in which I used Scrapy integrated with Django

### Django

At the end of settings.py we have these lines, to specify the django settings and to setup django itself

```sh
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath('.')))
os.environ['DJANGO_SETTINGS_MODULE'] = 'aste.production'

import django
django.setup()
```
Thanks that in the pipeline we can use django functionalities to save crawled data in specific models
