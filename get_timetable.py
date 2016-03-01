# -*- coding: utf-8 -*-
import requests
from bs4 import BeautifulSoup
from time import sleep
from urllib2 import urlopen
from collections import OrderedDict
import re
from dateutil import parser
import sqlite3 as sql


RADIO_TYPE = "XMLSpreadsheet;studentsetxmlurl;SWSCUST+StudentSet+XMLSpreadsheet"

ROOMS_RE = re.compile('([A-D]\d \d{3})')
NON_DIGITS_RE = re.compile('[\D]+')

SQL_TABLE = "(Week INT, Weekday VARCHAR(3), Date VARCHAR(10), StartTime VARCHAR(5), EndTime VARCHAR(5), Course VARCHAR(16), Type VARCHAR(10), Info VARCHAR(64), Rooms VARCHAR(64));"

# These are parameters that will be fetched from the page.
auto_params = ["__EVENTTARGET", "__EVENTARGUMENT", "__LASTFOCUS", "__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION", "tLinkType",
			  "tWildcard", 'bGetTimetable']

day_convert = {"Man": "Mon", "Tir": "Tue", "Ons": "Wed", "Tor": "Thu", "Fre": "Fri", "Lør": "Sat"}


def get_timetable(days, weeks, subject_code, season, csv=False):
	url = "http://timeplan.uia.no/swsuia" + season + "/public/no/default.aspx"
	html = ""

	# We need to set these parameters ourselves
	params = {
		'RadioType': RADIO_TYPE,
		'lbDays': days,
		'lbWeeks': ";".join(str(_) for _ in weeks),
		'dlObject': subject_code
	}

	with requests.Session() as s:
		r = False
		soup = False
		params['__EVENTVALIDATION'] = False

		# Try until we get the needed parameters
		while not params['__EVENTVALIDATION']:
			sleep(0.5)
			r = s.get("http://timeplan.uia.no/swsuia" + season + "/public/no/login.aspx")
			soup = BeautifulSoup(r.text, 'lxml')
			params['__EVENTVALIDATION'] = soup.find(id='__EVENTVALIDATION')

		# Get parameters from the page
		for p in auto_params:
			thing = soup.find(id=p)
			if thing != None:
				val = thing.get('value')
				if val:
					params[p] = val
				else:
					params[p] = ""
			else:
				params[p] = p

		# Get the actual time table, with params as the payload
		r = s.post(url, data=params)

		soup = BeautifulSoup(r.text, 'lxml')

		return convert_to_table_format(r.text.encode('utf-8'), csv)

def get_subject_codes(season):
	results = OrderedDict()

	with requests.Session() as s:
		r = False
		soup = False
		l = False

		# Try until we get what we want
		while not l:
			sleep(0.5)
			r = s.get("http://timeplan.uia.no/swsuia" + season + "/public/no/login.aspx")
			soup = BeautifulSoup(r.text, 'lxml')
			l = soup.find(id='dlObject')

		# Make an ordered dict with subject titles and their respective codes
		if l != None:
			for o in l.find_all('option'):
				results.update({o.getText(): o.get('value')})

	return results

def convert_to_table_format(html, csv):
	soup = BeautifulSoup(html, 'lxml')
	tab = soup.find_all('table')
	table = []
	if csv: table = ""
	week_no = 0

	for week_table in tab:
		# For each week table
		for week_row in week_table:
			# Each row per table.
			row_type = week_row.get('class')

			# tr1 means this is a table header
			if "tr1" in row_type:
				week_info = week_row.find('td', {"class": "td1"})
				week_no = week_info.getText().encode('utf-8').split(",")[0][4:]
				if csv: table += "\n"

			# tr2 - this is actual content
			if "tr2" in row_type:
				row = week_row.find_all('td')
				if csv:
					table += get_row_info(row, week_no, csv)
				else:
					table.append(get_row_info(row, week_no, csv))

	return table

def get_row_info(row, week_no, csv):
	week_day = ""
	date = ""
	start_time = ""
	end_time = ""
	course_code = ""
	course_type = ""
	info = ""
	rooms = ""

	for i in range(len(row)):
		if len(row[i].getText()) > 0:
			# Get rid of any surrounding whitespace
			val = row[i].getText().encode('utf-8').strip()

			# Convert weekdays
			if i == 0:
				week_day = day_convert[val]

			# Properly format dates (these are English)
			if i == 1:
				date = parser.parse(val).isoformat()[:10]

			# Split the to-from times, have different columns
			if i == 2:
				time_list = val.split("-")
				start_time = time_list[0]
				end_time = time_list[1]

			# Extract info like subject code, type of class
			elif i == 3:
				# A class has at least two fields: The course code and the type. After this there can be some info.
				val = val[1:].split("/")

				course_code = val[0]

				if "forel" in val[1].lower():
					course_type = "Lecture"
				else: 
					course_type = "Practice"

				# Info can have some irrelevant numbers, so filter those out
				info = [_ for _ in val[2:] if re.findall(NON_DIGITS_RE, _)]
				info = "".join(info)

			# Find and extract rooms
			elif i == 4:
				listed_rooms = re.findall(ROOMS_RE, val)
				rooms = "/".join(listed_rooms)

			# No need to add names of lecturers etc
			elif i == 5:
				continue

	vals = (week_no, week_day, date, start_time, end_time, course_code, course_type, info, rooms)
	if csv: vals = ";".join(vals) + ";\n"
	return vals


def add_to_db(timetable, code):
	try: 
		db_con = sql.connect("timetable.db")
		db_con.text_factory = str
		with db_con:
			table = "\"" + code + "\""
			cur = db_con.cursor()
			cur.execute("CREATE TABLE IF NOT EXISTS " + table + SQL_TABLE)
			cur.executemany("INSERT INTO " + table + " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);", timetable)
			print "Timetable inserted into database"

	except sql.Error, e:
		print "SQL error:", str(e)


# "t" means this week
weeks = "t"
# weeks = range(1,31)

# Can be 1-3 (mon-wed), 4-6 (thu-sat) or 1-6 (mon-sat)
days = "1-6"

# "v" for spring, "h" for autumn
period = "v"

# Get a valid code through get_subject_codes
subject_code = "#SPLUSE0C745"

# Example for getting the time table and printing it out as csv
print get_timetable(days, weeks, subject_code, period, csv=True)

# Example for getting the time table and adding it to the database
# tab = get_timetable(days, weeks, subject_code, period)
# add_to_db(tab, subject_code)

# Example for printing subject codes
# subject_codes = get_subject_codes("v")
# for k, v in subject_codes.items(): print k.encode('utf-8') + ": " + v.encode('utf-8')

