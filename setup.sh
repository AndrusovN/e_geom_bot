!/bin/bash


python3 -m venv venv
. venv/bin/activate
echo "{\"passed\": []}" > passed_kids.json
pip3 install -r requirements.txt