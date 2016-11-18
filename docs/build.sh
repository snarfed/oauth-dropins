#!/bin/bash
#
# Preprocesses docs and runs Sphinx (apidoc and build) to build the HTML docs.
#
# Still imperfect. After pandoc generates index.rst, you need to revise the
# header and remove the manual TOC and the footer images.
set -e

absfile=`readlink -f $0`
cd `dirname $absfile`

# pandoc --from=markdown --to=rst ../README.md \
#   | sed -E 's/```/`/; s/`` </ </' \
#   > index.rst

# sphinx-apidoc -f -o source ../oauth_dropins \
#   ../oauth_dropins/{webutil,}/{appengine_config.py,test}

sphinx-build -b html . _build/html
