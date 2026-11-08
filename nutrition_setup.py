"""Standalone setup CLI for nutrition sources, target profiles and dry-run optimization."""
from __future__ import annotations
import argparse
from datetime import date
import json
from pathlib import Path
import sys

from src.journal_core.fooddata import search,fetch,food_to_row,write_reference
from src.journal_core.profiles import NutritionProfiles, load_profiles, save_profiles, target_for_person, MacroTarget
from src.journal_core.nutrition import reference_file,load_reference
from src.journal_core.state import load_menu
from src.journal_core.recipe_parser import load_catalog
from src.journal_core.optimizer import propose_day
from src.journal_core.weekly import monday_start


def main():
    p=argparse.ArgumentParser(description='CrewAI Journal verified nutrition setup; profiles remain local')
    group=p.add_subparsers(dest='group',required=True)
    fdc=group.add_parser('fdc')
    sub=fdc.add_subparsers(dest='action',required=True)
    s=sub.add_parser('search');s.add_argument('query')
    x=sub.add_parser('import'); x.add_argument('--id',type=int,required=True)
    x.add_argument('--ingredient',required=True);x.add_argument('--state',required=True,
        choices=['raw','cooked','drained','as_served']);x.add_argument('--replace',action='store_true')
    ref=group.add_parser('reference');ref.add_argument('action',choices=['status'])
    profiles=group.add_parser('profiles');profiles.add_argument('action',choices=['show','import']);profiles.add_argument('--file')
    opt=group.add_parser('optimize');opt.add_argument('--date',required=True);opt.add_argument('--person',choices=['person_a','person_b'],required=True);opt.add_argument('--load',choices=['rest','easy','moderate','long'],help='Manual person-specific day activity override for preview')
    args=p.parse_args()
    try:
        if args.group=='fdc':
            if args.action=='search':
                result=search(args.query)
            else:
                original=fetch(args.id)
                result=food_to_row(original,ingredient=args.ingredient,state=args.state)
                print(json.dumps({'review_before_saving':result},ensure_ascii=False,indent=2))
                if input('Confirm this exact food/ingredient match? [y/N]: ').strip().lower()!='y':
                    print('Not saved');return 1
                write_reference(reference_file(),result,replace=args.replace)
                result={'saved_to':str(reference_file()),'mapping':result}
        elif args.group=='reference':
            path=reference_file()
            result={'path':str(path),'exists':path.exists(),
                    'count':len(load_reference(path)) if path.exists() else 0}
        elif args.group=='profiles':
            if args.action=='show':
                obj=load_profiles();result=obj.model_dump() if obj else {'status':'not_configured'}
            else:
                if not args.file:raise ValueError('--file path required')
                obj=NutritionProfiles.model_validate_json(Path(args.file).read_text(encoding='utf-8'))
                if not obj.verified_by_user:raise ValueError('Set verified_by_user: true after checking person-specific targets')
                result={'saved_to':str(save_profiles(obj))}
        else:
            d=date.fromisoformat(args.date)
            menu=load_menu(monday_start(d).isoformat())
            if not menu or menu.status!='approved':raise ValueError('Approved menu for date required')
            profile=load_profiles()
            if not profile or not profile.verified_by_user:raise ValueError('User-approved nutrition profiles required')
            status=target_for_person(profile,args.person,d,manual_load=args.load)
            if status['status']!='ready':raise ValueError(status['reason'])
            target=MacroTarget(**status['target'])
            result={'date':d.isoformat(),'activity':status,
                    'proposal':propose_day(menu,load_catalog(),(d-monday_start(d)).days,args.person,target)}
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except (ValueError,OSError,KeyError) as exc:
        print(f'ERROR: {exc}',file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())
