#!/usr/bin/env python

import os
import sys


bin_dir = os.path.dirname(os.path.realpath(__file__))
pyscript_dir = os.path.abspath(os.path.join(bin_dir, os.pardir))
lib_dir = os.path.join(pyscript_dir, 'lib')
#lib_dir = os.path.join(pyscript_dir, 'lib/pyscript')
#config_dir = os.path.join(pyscript_dir, 'config')
tests_dir = os.path.join(pyscript_dir, 'test')
sys.path.insert(0, lib_dir)
#sys.path.insert(0, config_dir)
sys.path.insert(0, tests_dir)
sys.dont_write_bytecode = True

#from setup import main
from pyscript.setup import main

if __name__ == '__main__':
    main()

