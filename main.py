import sqlite3
import re
import subprocess
import requests

from flask import Flask, render_template, g, request

app = Flask(__name__)
DATABASE = 'hooks.db'


# Sqlite3 utilities
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
    return db


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


def sql_db(query, args=()):
    cur = get_db().cursor().execute(query, args)
    get_db().commit()
    cur.close()


def query_db(query, args=(), one=False):
    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv


# Check if kernel version exists
def check_version(ma, mi):
    test_url = 'https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git/tree/?h=v'

    if requests.get(test_url + ma + '.' + mi).status_code == 200:
        return mi, True
    else:
        return str(int(mi) - 1), False


# Add Linux kernel versions to DB
def populate_version():
    versions = []
    url = 'https://www.kernel.org/releases.json'
    gitweb = 'https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git/plain/include/linux/'
    filepath = 'lsm_hooks.h'
    filepath_old = 'security.h'

    response = requests.get(url)
    data = response.json()

    sql_db('CREATE TABLE if not exists versions(id integer primary key autoincrement, Name Varchar UNIQUE, Url VarChar)')

    for r in data['releases']:
        m = re.search('^(([0-9])\.([0-9]*))\.', r['version'])
        if m:
            if versions:
                major, minor = versions[-1].split('.')
                if int(major) == int(m.group(2)):
                    if int(minor) < int(m.group(3)):
                        versions.append(m.group(1))
                else:
                    versions.append(m.group(1))
            else:
                versions.append(m.group(1))

    for v in versions:
        major, minor = v.split('.')
        cond = True
        while cond:
            minor, cond = check_version(major, str(int(minor) + 1))

        for i in range(int(minor), -1, -1):
            ver = major + '.' + str(i)
            if (int(major) == 4 and int(i) > 1) or (int(major) >= 5):
                url = gitweb + filepath + "?h=v" + ver
            else:
                url = gitweb + filepath_old + "?h=v" + ver

            sql_db(
                'INSERT OR REPLACE INTO versions (Name, Url) VALUES (?, ?)', (ver, url))


# Retrieve hooks from an online source and put them in a list
def hooks(url):
    cmd = r"wget -O - -q '" + url + \
        r"' | tr -d '\n'|sed -e 's/\tvoid (/\nvoid (/g' -e 's/\tint (/\nint (/g'|sed  -e 's/;.*//'| sed -r 's/[\t ]{2,20}/ /g'| egrep '^int|^void'| sed -r 's/^[ \t]*([^\)]*) \(\*([^\)]*)\).*\((.*)\).*/\1|\2|\3/'"
    output = subprocess.check_output(cmd, stderr=subprocess.STDOUT, shell=True)

    l = []
    for o in output.decode("utf-8").split('\n'):
        output_list = o.split('|')
        l.append(output_list)

    return l[:-1]


# Find an item by name
def item_by_name(name, list_dst):
    for item in list_dst:
        if name == item[1]:
            return item


# Builds HTML string
def build_function(item):
    return item[0] + " <b>" + item[1] + '</b>(' + item[2] + ')'


# Compare hooks in two versions of the kernel
@app.route('/compare', methods=['POST'])
def compare():
    result = request.form
    result_dict = result.to_dict(flat=False)
    dict_a = query_db('select * from versions where name=?',
                      [result_dict['version'][0]], one=True)
    dict_b = query_db('select * from versions where name=?',
                      [result_dict['version'][1]], one=True)

    list_a = hooks(dict_a[2])
    list_b = hooks(dict_b[2])

    result_a = []
    result_b = []

    for item in list_a:
        if item not in list_b:
            item_b = item_by_name(item[1], list_b)
            if not item_b:  # item only in A
                result_a.append((build_function(item), 'green'))
                result_b.append(('-', 'green'))
            else:  # item in A and B but they are different
                result_a.append((build_function(item), 'orange'))
                result_b.append(
                    (build_function(item_by_name(item[1], list_b)), 'orange'))
        else:  # item in A and B
            result_a.append((build_function(item), 'white'))
            result_b.append((build_function(item), 'white'))

    for item_b in list_b:
        if item_b not in list_a:
            item_a = item_by_name(item_b[1], list_a)
            if not item_a:
                result_b.append((build_function(item_b), 'red'))
                result_a.append(('-', 'red'))

    return render_template('results.html', versions=result_dict, result_a=result_a, result_b=result_b)


# Main page
@app.route('/')
def index():
    populate_version()

    vs = query_db('select * from versions')
    return render_template('index.html', versions=vs)
