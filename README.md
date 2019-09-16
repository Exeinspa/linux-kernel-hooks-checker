Compare hooks in two versions of the Linux kernel.

# Getting started

## Setup
Install dependencies:

`sudo pip3 install -r requirements.txt`


## Usage
Run with:

`export FLASK_APP=main`

`export FLASK_ENV=development`

`flask run`

or

`gunicorn -w 4 main:app`
