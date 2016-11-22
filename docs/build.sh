#!/bin/bash
#
# Preprocesses docs and runs Sphinx (apidoc and build) to build the HTML docs.
set -e

absfile=`readlink -f $0`
cd `dirname $absfile`

# sphinx-apidoc -f -o source ../oauth_dropins \
#   ../oauth_dropins/{webutil,}/{appengine_config.py,test}

rm -f index.rst
cat > index.rst <<EOF
oauth-dropins documentation
===========================

EOF

tail -n +15 ../README.md \
  | pandoc --from=markdown --to=rst \
  | sed -E 's/```/`/; s/`` </ </' \
  >> index.rst

source ../local/bin/activate

# Run sphinx in the virtualenv's python interpreter so it can import packages
# installed in the virtualenv.
python `which sphinx-build` -b html . _build/html

