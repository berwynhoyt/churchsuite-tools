#!/usr/bin/env python3
""" Select people who are regular or irregular and/or people who are in a tag or flow. Optionally add them to a tag/flow. """

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
class NoFlowTag(Exception): pass
class InvalidStatus(Exception): pass

__version__ = '1.0.0'

def attendance_records(cs, weeks=31, days=['sunday']):
    """ Return dict of attendance records (by record_id) that fall on specified days in the previous number of weeks specified """
    today = date.today()
    # Get the date of n weeks ago
    is_after = today - timedelta(days=7*weeks)
    records = cs.get('attendance/records', days=days, is_after=is_after)
    records = {r.id: r for r in records}  # convert to dict by record ID
    return records

def add_attendance(cs, people, records):
    """ Given a SimpleNamespace list of people, add a dates_present attribute to each person
        such that people[n].dates_present will contain a set() of dates they attended.
        cs: Churchsuite instance
        records: a dict of attendance records produced by attendance_records()
    """
    for person in people:
        person.dates_present = set()
    present = cs.get('attendance/record_contacts', record_ids=list(records.keys()))
    # Arrange people in a dict by person id so we can look up a person quickly to add each attendance date
    people_by_id = {p.id: p for p in people}
    for attender in present:
        people_by_id[attender.contact_id].dates_present.add(records[attender.record_id].date)

_tag_cache = {}  # cache of (tag_name,status) which have had their members fetched

def tag_members(cs, tag_name, status='active', message=''):
    """ Return a dict of (default active) tag members, indexed by their person_id; each dict value is set to a SimpleNamespace of the person's details.
        Cache results in case the same (tag_name, status) combination is requested later.
        Raise NoTag exception if tag doesn't exist, with 'message' appended to the error message.
        Raise InvalidStatus if status is not one of the options below.
    """
    status_options = ('active', 'archived', 'pending')
    if status not in status_options:
        raise InvalidStatus(f"Parameter 'status' must be one of: {status_options}")
    key = (tag_name, status)
    if key in _tag_cache:
        return _tag_cache[key]
    tag_id = cs.get_tag_id(tag_name)
    if tag_id is None:
        raise NoTag(f"Tag '{tag_name}' does not exist. {message}")
    people = cs.get('addressbook/contacts', tag_ids=[tag_id], status=status)
    people = {person.id: person for person in people}
    _tag_cache[key] = people
    return people

def append_defaults(l, defaults):
    """ Append items to list 'l' from 'defaults', as necessary to fill it up to len(defaults). Return 'l' """
    l += defaults[len(l):]
    return l

def filter_by_attendance(cs, people):
    """ Return list of people filtered by attendance specified in args.attendance """
    if args.attendance: return people
    # Merge in attendance records for each person
    records = attendance_records(cs, weeks=args.attendance[2])
    print(f"Examining {len(records)} sunday attendances recorded in the past {args.attendance[2]} weeks.")
    add_attendance(cs, people, records)
    # Categorise people by attendance frequency
    attender_by_freq = defaultdict(list)
    for person in people:
        freq = len(person.dates_present)
        attender_by_freq[freq].append(person)
    # Collate a list of both regulars and irregulars
    regulars, irregulars = [], []
    if args.verbose: print(f"\nIrregular attenders:")
    regular = False
    for freq in sorted(attender_by_freq):
        if freq >= args.attendance[1] and not regular:
            if args.verbose: print(f"\nRegular attenders:")
            regular = True
        if args.verbose:
            people = ', '.join(' '.join([p.first_name, p.last_name]) for p in sorted(attender_by_freq[freq], key=attrgetter('last_name', 'first_name')))
            print(f"  {freq}/{args.attendance[2]} sundays: {people}")
        if regular:
            regulars += attender_by_freq[freq]
        else:
            irregulars += attender_by_freq[freq]
    # Sort by just to keep output consistent (by last_name)
    regulars.sort(key=attrgetter('last_name', 'first_name', 'middle_name'))
    irregulars.sort(key=attrgetter('last_name', 'first_name', 'middle_name'))
    if args.verbose: print(f"\nFound {len(regulars)} regulars and {len(irregulars)} irregulars.")

    return irregulars if args.attendance[0] else regulars

def filter_by_flow_tag(cs, people, flow_tag_names=list(), message=''):
    """ Return a filtered list of people, including only those in the given list of flow or tag names.
        People in flow or tag names that are prefixed with '-' are NOT included. An empty list lets everyone through.
        Each name in the flow_tag_names list must reference a flow or tag name (flows take priority).
        NoFlowTag error will be raised if a flow or tag is not found
    """
    if not flow_tag_names: return people
    inclusions, exclusions = set(), set()
    in_flows, not_in_flows = [], []
    for flow_tag in flow_tag_names:
        not_in = flow_tag.startswith('-')
        flow_tag = flow_tag[int(not_in):]
        flow_id = cs.get_flow_id(flow_tag)
        if flow_id:
            if args.verbose: print(f"{'Excluding' if not_in else 'Including'} people in flow '{flow_tag}'")
            (not_in_flows if not_in else in_flows).append(flow_id)
            continue
        try:
            tagged = tag_members(cs, flow_tag)
            if args.verbose: print(f"{'Excluding' if not_in else 'Including'} people in tag '{flow_tag}'")
            if not_in:
                exclusions |= set([*tagged])  # OR together all exclusion sets
            else:
                inclusions |= set([*tagged])  # AND together all inclusion sets
        except NoTag:
            raise NoFlowTag(f"No flow or tag is visible to '{flow_tag}'. {message}")
    # Add people from flows to inclusions and exclusions outside the FOR loop above because
    # people in many flows can be requested all in one API request which is more efficent
    if in_flows:
        trackings = cs.get('addressbook/flow_trackings', flow_ids=in_flows)
        print([t.person.id for t in trackings])
        inclusions |= set([t.person.id for t in trackings])
    if not_in_flows:
        trackings = cs.get('addressbook/flow_trackings', flow_ids=not_in_flows)
        exclusions |= set([t.person.id for t in trackings])
    return [p for p in people if (not inclusions or p.id in inclusions) and p.id not in exclusions]

def main(args):
    if args.version:
        print(__version__)
        sys.exit()

    # Set logging level based on -v flag
    log_level = logging.WARNING - 10*args.verbose
    logging.basicConfig(level=log_level, format=f'%(levelname)s: %(message)s')

    import config
    cs = churchsuite.Churchsuite(auth=(config.USER_CLIENT_ID, config.USER_CLIENT_SECRET), scope=scope)
    people = cs.get('addressbook/contacts', status='active')  # fetch everyone
    people = filter_by_attendance(cs, people)
    people = filter_by_flow_tag(cs, people, args.filters, message='Specified with --in')
    print(f"\n* Identified {len(people)} people:", ', '.join(p.first_name+' '+p.last_name for p in people) or 'nobody')


if __name__ == "__main__":
    def parse_attendance(freq):
        """ Parse attendance frequency argument of style: [<]4/8. """
        try:
            n, m = freq.strip('<').split('/')
            return [freq.startswith('<'), int(n), int(m)]
        except:
            raise argparse.ArgumentTypeError(f"{freq} invalid: must be two integers separated by /")

    parser = argparse.ArgumentParser(
        usage="%(prog)s [--help] [options]",
        description=
            "Select people who are regular or irregular and/or people who are in a tag or flow. Optionally add them to a tag/flow.\n"
            "Examples:\n"
            "  people.py --attendance   4/8  --in -Members,-Followup          --add-to-flow Followup\n"
            '  people.py --attendance "<2/8" --in  Members,-Followup,-ShutIn  --add-to-flow Followup\n'
            "  people.py --in TrainingExpired --add-to-flow FollowupTraining",
    )
    parser.add_argument('--attendance', type=parse_attendance,
        help='Select attendance frequency: e.g. 3/8 selects regulars: those who attend at least 3 of 8 weeks; but "<3/8" selects irregulars: those who attend less than that.')
    parser.add_argument('--in', metavar='flow,-flow,tag,-tag,...', type=lambda flows: [f.strip() for f in flows.split(',')], default=list(),
        help="Include regulars or irregulars only if they are also in ANY of the specified list of flows or tags, and NOT in any of the -flows or -tags. "
            "A typical use would be finding newcomers who aren't members and aren't in a flow: regulars 4/8 --in=-Members,-Followup. "
            "Another example to find members who haven't come for a while: irregulars 1/8 --in=Members,-Followup. "
            "Note: Flow/tag names that contain spaces must be enclose in quotes.")
    parser.add_argument('--add-to-flow', type=str,
        help="Add to the specified flow any people identified as regulars/irregulars.")
    parser.add_argument('--add-to-tag', type=str,
        help="Add to the specified tag any people identified as regulars/irregulars.")
    parser.add_argument('-v', '--verbose', action='count', default=0, 
        help="Increase verbosity level (e.g., -vv) to, for example, "
            "print all regulars and irregulars found before they are filtered by any flows/tags specified by --in.")
    parser.add_argument('--version', action='store_true', 
        help="Print version number of this script and exit.")
    args = parser.parse_args()
    args.filters = getattr(args, 'in') # cannot read args.in because 'in' is a reserved word

    try:
        main(args)
    except (NoTag, NoFlowTag) as e:
        print(f"Error: {e}", file=sys.stderr)
