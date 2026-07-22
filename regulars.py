#!/usr/bin/env python3
""" Tag regular attenders if they come n times in the past m weeks """

import sys
import pprint
import argparse
import logging

from types import SimpleNamespace
from datetime import date, timedelta
from collections import defaultdict
from operator import attrgetter

import requests
import churchsuite

scope = ['attendance.read', 'addressbook.read', 'addressbook.write']

__version__ = '1.0.0'

def attendance_records(cs, weeks=31, days=['sunday']):
    """ Return dict of attendance records (by record_id) that fall on specified days in the previous number of weeks specified """
    today = date.today()
    # Get the date of n weeks ago
    is_after = today - timedelta(days=7*weeks)
    records = cs.get('attendance/records', days=days, is_after=is_after)
    records = {r.id: r for r in records}  # convert to dict by record ID
    return records

def attendance_stats(cs, records):
    """ Return dict of attenders as SimpleNamespace(id, first_name, last_name, dates_present) indexed by contact_id
        cs: Churchsuite instance
        records: a dict of attendance records produced by attendance_records()
    """
    attenders = {}
    # Fetch all people into dict, initially with their 'dates_present' set empty
    people = cs.get('addressbook/contacts', status='active')
    for person in people:
        attenders[person.id] = SimpleNamespace(id=person.id, first_name=person.first_name, last_name=person.last_name, dates_present=set())

    present = cs.get('attendance/record_contacts', record_ids=list(records.keys()))
    for person in present:
        contact_id = person.contact_id
        attenders[contact_id].dates_present.add(records[person.record_id].date)

    return attenders

def main():
    parser = argparse.ArgumentParser(description="Tag regular attenders so that the tags can be used by ChurchSuite filters.")
    parser.add_argument('frequency', help="Specify attendance frequency of a regular as n/m, meaning n of the past m weeks, e.g.: 4/8")
    parser.add_argument('--tag', type=str, nargs='?', const=True, help="Specify tag to assign to matching people (default='Regular'); if --tag omitted, do not tag")
    parser.add_argument('--irregular', action='store_true', help="If --tag is specified, tag only people who do NOT match frequency (also default tag name to 'Irregular')")
    parser.add_argument('-v', '--verbose', action='count', default=0, help="Increase verbosity level (e.g., -vv).")
    parser.add_argument('--version', action='store_true', help="Print version number of this script and exit.")
    args = parser.parse_args()

    if args.tag is True:
        args.tag = 'Irregular' if args.irregular else 'Regular'

    if args.version:
        print(__version__)
        sys.exit()

    n, m = args.frequency.split('/')
    args.frequency = int(n), int(m)

    # Set logging level based on -v flag
    log_level = logging.WARNING - 10*args.verbose
    logging.basicConfig(level=log_level, format=f'%(levelname)s: %(message)s')

    import config
    cs = churchsuite.Churchsuite(auth=(config.USER_CLIENT_ID, config.USER_CLIENT_SECRET), scope=scope)

    # Fetch attendance records
    records = attendance_records(cs, weeks=args.frequency[1])
    print(f"Examining {len(records)} sunday attendances recorded in the past {args.frequency[1]} weeks.")

    # Fetch attendance stats for each person
    attender_stats = attendance_stats(cs, records)
    attenders = defaultdict(list)
    for person in attender_stats.values():
        freq = len(person.dates_present)
        attenders[freq].append(person)

    regulars, irregulars = [], []
    print(f"\nIrregular attenders:")
    regular = False
    for freq in sorted(attenders):
        if freq > args.frequency[0] and not regular:
            print(f"\nRegular attenders:")
            regular = True
        people = ', '.join(' '.join((p.first_name, p.last_name)) for p in sorted(attenders[freq], key=attrgetter('first_name', 'last_name')))
        print(f"  {freq}/{args.frequency[1]} sundays: {people}")
        if regular:
            regulars += attenders[freq]
        else:
            irregulars += attenders[freq]

    # Display actions that will be taken
    print(f"\nFound {len(regulars)} regulars and {len(irregulars)} irregulars.")

    # Create tag in ChurchSuite
    if args.tag:
        taggable = irregulars if args.irregular else regulars
        print(f"\nTagging {len(taggable)} {'irregulars' if args.irregular else 'regulars'} as '{args.tag}':")
        data = cs.get('addressbook/tags', q=args.tag)
        if data:
            tag_id = data[0].id
        else:
            data = cs.post('addressbook/tags', name=args.tag, is_smart=False, colour='brown')
            tag_id = data.id
        for person in sorted(taggable, key=attrgetter('first_name', 'last_name')):
            print(f"{' '.join((person.first_name, person.last_name))}", end='; ', flush=True)
            cs.post('addressbook/tag_resources', person=dict(type='addressbook_contact', id=person.id), tag_id=tag_id)
        print("\nSuccess.")

if __name__ == "__main__":
    main()
