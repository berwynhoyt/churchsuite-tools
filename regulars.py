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

# Exceptions
class NoTag(Exception): pass

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
    # Fetch all people into dict, initially with their 'dates_present' set empty
    people = cs.get('addressbook/contacts', status='active')
    attenders = {person.id: SimpleNamespace(id=person.id, first_name=person.first_name, last_name=person.last_name, dates_present=set()) for person in people}

    present = cs.get('attendance/record_contacts', record_ids=list(records.keys()))
    for person in present:
        contact_id = person.contact_id
        attenders[contact_id].dates_present.add(records[person.record_id].date)

    return attenders

_tag_cache = {}  # cache of (tag_name,status) which have had their members fetched

def tag_members(cs, tag_name, status='active'):
    """ Return a dict of (default active) tag members, indexed by person_id; each value set to a SimpleNamespace of the person's details.
        Cache results in case the same (tag_name,status) combination is requested later.
        Raise NoTag exception if tag doesn't exist.
    """
    key = (tag_name, status)
    if key in _tag_cache:
        return _tag_cache[key]
    tag_id = cs.get_tag_id(tag_name)
    if tag_id is None:
        raise NoTag(f"Specified tag '{tag_name}' does not exist")
    people = cs.get('addressbook/contacts', tag_ids=[tag_id], status=status)
    people = {person.id: person for person in people}
    _tag_cache[key] = people
    return people

def append_defaults(l, defaults):
    """ Append items to list 'l' from 'defaults', as necessary to fill it up to len(defaults). Return 'l' """
    l += defaults[len(l):]
    return l


def main(args):
    if args.version:
        print(__version__)
        sys.exit()

    # Set logging level based on -v flag
    log_level = logging.WARNING - 10*args.verbose
    logging.basicConfig(level=log_level, format=f'%(levelname)s: %(message)s')

    import config
    cs = churchsuite.Churchsuite(auth=(config.USER_CLIENT_ID, config.USER_CLIENT_SECRET), scope=scope)

    # Fetch attendance records
    records = attendance_records(cs, weeks=args.frequency[1])
    print(f"Examining {len(records)} sunday attendances recorded in the past {args.frequency[1]} weeks.")

    # Fetch attendance stats for each person
    attenders = attendance_stats(cs, records)
    attender_by_freq = defaultdict(list)
    for person in attenders.values():
        freq = len(person.dates_present)
        attender_by_freq[freq].append(person)

    regulars, irregulars = [], []
    print(f"\nIrregular attenders:")
    regular = False
    for freq in sorted(attender_by_freq):
        if freq > args.frequency[0] and not regular:
            print(f"\nRegular attenders:")
            regular = True
        people = ', '.join(' '.join((p.first_name, p.last_name)) for p in sorted(attender_by_freq[freq], key=attrgetter('first_name', 'last_name')))
        print(f"  {freq}/{args.frequency[1]} sundays: {people}")
        if regular:
            regulars += attender_by_freq[freq]
        else:
            irregulars += attender_by_freq[freq]
    print(f"\nFound {len(regulars)} regulars and {len(irregulars)} irregulars.")

    # Tag regulars/irregulars in ChurchSuite as specified on the command line
    if args.tag:
        for tag, target in [(args.tag, regulars), (args.tag_irregulars, irregulars)]:
            print(f"\nTagging {len(target)} {'regulars' if target==regulars else 'irregulars'} as '{tag}':")
            tag_id = cs.get_tag_id(tag)
            # Create tag if it doesn't exit
            if not tag_id:
                data = cs.post('addressbook/tags', name=tag, is_smart=False, colour='brown')
                tag_id = data.id
            for person in sorted(target, key=attrgetter('first_name', 'last_name')):
                print(f"{' '.join((person.first_name, person.last_name))}", end='; ', flush=True)
                cs.post('addressbook/tag_resources', person=dict(type='addressbook_contact', id=person.id), tag_id=tag_id)
            print('\n')

    if args.regular_newcomers is not None:
        print('\nNewcomers who are regular (>={args.frequency} weeks) so should be added to a newcomer flow:')
        regular_newcomers, regular_newcomers_inflow, regular_newcomers_noflow = [], [], []
        append_defaults(args.regular_newcomers, defaults=['Current Parishioner', 'In any flow'])
        member_tag, flow_tag = args.regular_newcomers
        members = tag_members(cs, member_tag)
        flow_members = tag_members(cs, flow_tag)
        # identify regulars if they are NOT members
        regular_newcomers = [person for person in regulars if person.id not in members]
        regular_newcomers_inflow = [person for person in regular_newcomers if person.id in flow_members]
        regular_newcomers_noflow = [person for person in regular_newcomers if person.id not in flow_members]
        print('  * Need a flow:       ', ', '.join(p.first_name+' '+p.last_name for p in regular_newcomers_noflow) or 'nobody')
        print('  * Already in a flow: ', ', '.join(p.first_name+' '+p.last_name for p in regular_newcomers_inflow) or 'nobody')

    if args.irregular_members is not None:
        print(f'\nMembers who are irregular (<{args.frequency} weeks) so should be added to a followup flow:')
        irregular_members, irregular_members_inflow, irregular_members_noflow = [], [], []
        append_defaults(args.irregular_members, defaults=['Current Parishioner', 'In any flow'])
        member_tag, flow_tag = args.irregular_members
        members = tag_members(cs, member_tag)
        flow_members = tag_members(cs, flow_tag)
        # identify irregulars who ARE members
        irregular_members = [person for person in irregulars if person.id in members]
        irregular_members_inflow = [person for person in irregular_members if person.id in flow_members]
        irregular_members_noflow = [person for person in irregular_members if person.id not in flow_members]
        print('  * Need a flow:       ', ', '.join(p.first_name+' '+p.last_name for p in irregular_members_noflow) or 'nobody')
        print('  * Already in a flow: ', ', '.join(p.first_name+' '+p.last_name for p in irregular_members_inflow) or 'nobody')

    # There is currently no ChurchSuite API call to add to a flow, so email someone if --email supplied
    if args.regular_newcomers is not None or args.irregular_members is not None:
        print('email someone')

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        usage="%(prog)s [--help] [options] frequency",
        description=
            "Tag regular/irregular attenders, or highlight/email about new regulars and irregular members.\n"
            "When ChurchSuite implements the add-to-flow API, this will support it.\n"
            "In the meantime, it simply displays and emails them.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('frequency', 
        help="4/8 (for example) defines a regular as attending at least 4 of 8 weeks")
    parser.add_argument('--tag', type=str, nargs='?', const='Regular', 
        help="Tag regulars in ChurchSuite (default='Regular')")
    parser.add_argument('--tag-irregulars', type=str, nargs='?', const='Irregular', 
        help="Tag irregulars in ChurchSuite (default='Irregular')")
    parser.add_argument('--regular-newcomers', type=lambda string: string.split(','), nargs='?', const=[],
        help="Optionally specify tag names: member_tag[,flow_tag]. "
            "Print/email a list of REGULARS NEWCOMERS if they are NOT in member_tag and are not already in a flow. "
            "Default names for member_tag and flow_tag are: 'Current Parishioner' and 'In any flow'. "
            "Membership in a flow cannot be tested directly by ChurchSuite API so is tested instead by membership in flow_tag "
            "which you must define in ChurchSuite in advance as a smart tag that tests whether the contact is in any flow.")
    parser.add_argument('--irregular-members', type=lambda string: string.split(','), nargs='?', const=[],
        help="Optionally specify tag names: member_tag[,flow_tag]. "
            "Print/email a list of IRREGULAR MEMBERS if they ARE in the member_tag and are not already in a flow. "
            "Default names for member_tag and flow_tag are: 'Current Parishioner' and 'In any Flow'. "
            "Membership in a flow cannot be tested directly by ChurchSuite API so is tested instead by membership in flow_tag "
            "which you must define in ChurchSuite in advance as a smart tag that tests whether the contact is in any flow.")
    parser.add_argument('-v', '--verbose', action='count', default=0, 
        help="Increase verbosity level (e.g., -vv).")
    parser.add_argument('--version', action='store_true', 
        help="Print version number of this script and exit.")
    args = parser.parse_args()

    n, m = args.frequency.split('/')
    args.frequency = int(n), int(m)

    main(args)
