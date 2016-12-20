#!/usr/bin/python

import random
import string

for x in range(0,5):
     data = ''.join(random.choice(string.letters + string.digits + 
                  "_" + string.punctuation)
            for i in range(0,random.randint(1, 152)))
     print(data)
     print("--------")
