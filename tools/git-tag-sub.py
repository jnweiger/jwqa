#! /usr/bin/python3
#
# find all tags at the current commit of this repo.
# Per default append the name of the current repo with @ to the tag to generate the tag name for submodules
# If --same is given, then tag-name-fmt is set to '{tag}'. --tag-name-fmt defaults to '{tag}@{repo}'
# where reponame is derived from the current toplevel repo.
# Iterate through submodules, push the tag after applyig a format.
# Warn for each git repo, if there are uncommited changes. (unless --unclean option is specified)
#
# (C) 2026 j.weigert@heinlein-support.de - distribute under GPLv2
#
# v0.1 20260217,    added some code to actually push tags into submodules
# v0.2 20260218,    properly implement --no-op
# v0.3 20260218,    submodule tagging wirks with sanitycheck, and filtered module list is fully supported.
# v0.4 20260219,    added GIT_TAG_SUB_FMT env var and {repo_md5}
# v0.5 20260220,    added short options, removed --check-only, which is obsoleted by --no-op.
#                   Add more early exits, consistently exit nonzero when in trouble.

# Oops, we definitly have to error out, when there is a dirty submodule. git diff then shows you something like
# --- a/src/test-sub2mod
# +++ b/src/test-sub2mod
# @@ -1 +1 @@
# -Subproject commit 012a120db7d601347271da4b9148e925c240d6d3
# +Subproject commit 012a120db7d601347271da4b9148e925c240d6d3-dirty
#
# Then you have to "git add src/test-sub2mod; git commit" to get things in sync.
# There is a built in sanity check, that will always complain about the above.
#
# TODO: sanity_check() and --unclean are currently all or nothing.
#       Can we e.g. accept uncommited code changes in the main repo? Tags operate on commited code anyway.

# Requires:
#   - python 3.5 or later,
#   - git
#   - pwd -P


import sys, os, argparse, subprocess, hashlib
from pathlib import Path
import fnmatch

__VERSION__ = '0.5'
verbose = False


def git(*args, no_op=False, chdir=None):
    """Run a git command and return its stdout stripped."""
    if type(args) == type(()) and type(args[0]) == type([]):
        # accept mutiple strings or a single list.
        args = args[0]

    if verbose:
        if no_op:
            print("# ", end='')
        if chdir is None:
            print("+ git " + ' '.join(args))
        else:
            print(f"+ (cd '{chdir}' && git " + ' '.join(args) + ')')

    if no_op:
        return ''

    result = subprocess.run(["git"] + list(args), stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=chdir, universal_newlines=True, check=False)
    if result.returncode != 0:
        sys.stderr.write(f"ERROR: git {' '.join(args)} failed:\n{result.stderr}\n")
        sys.exit(1)
    if verbose:
        print(result.stdout.strip())
    return result.stdout.strip()


def git_repo_name():
    origin = git("remote")
    if origin:
        url = git('remote', 'get-url', '--push', origin)
        top = url.split('/')[-1]
        if top.lower().endswith('.git'): top = top[:-4]
    else:
        path = git('rev-parse', '--show-toplevel')
        top = path.split('/')[-1]
    return(top)


def sanity_check(submodules=[]):
    # start with sanity checks.
    #
    # 0       0       LICENSE => LICENSE.md
    # 0       1       bar
    # 0       0       src/second-best/test-sub2mod
    main_numstat = git("diff-index", "--numstat", "HEAD")

    # task: starting relative to the current woking directory, check all the lines from main_numstat that start with any two digits, and if the remaining path contains a file(!) '.git' sub.
    # if so, we found a dirty submodule.
    dirty = []
    if len(main_numstat):
        dirty.append(main_numstat)

    for line in main_numstat.splitlines():
        words=line.split()
        # print("checking: ", words[2] + "/.git")
        if len(words) == 3 and os.path.isfile(words[2] + "/.git"):
            dirty.append(words[2])
            print("ERROR: sanity check failed: submodule not clean: ", words[2])
    if dirty:
        numstat_cnt = 0
        for mod in submodules:
            if len(git("diff-index", "--numstat", "HEAD", chdir=mod)):
                print(f"\nERROR: {mod}: submodule has uncommited changes.")
                numstat_cnt = numstat_cnt + 1
        if numstat_cnt:
            print(f"errors={numstat_cnt}: Everything must be cleanly committed or stashed before we can propagate tags.")
        return len(dirty)
    return 0


def glob_filter(names, patterns):
    # patterns = ['src/*', '*mod'patterns
    # returns ['src/import/best-ever-submod', 'src/second-best/test-sub2mod']
    return [s for s in names if any(fnmatch.fnmatch(s, p) for p in patterns)]


def main():
    global verbose

    try:
        repo_name = git_repo_name()
    except:
        repo_name = 'MAIN_REPO'
    repo_md5 = hashlib.md5(bytes(repo_name, 'utf-8')).hexdigest()

    parser = argparse.ArgumentParser(allow_abbrev=False, epilog="version: "+__VERSION__, description="Propagate git tags into submodules.")
    parser.def_fmt = os.getenv("GIT_TAG_SUB_FMT", "{tag}@{repo}")
    parser.def_mod = '*'

    parser.add_argument("--sametag", "--same", "-s", action="store_true", help="Do not modify the tag, when applying to submodules. Same as --tag-name-fmt='{tag}'.")
    parser.add_argument("--quiet", "-q", action="store_true", help="Print git commands.")
    parser.add_argument("--unclean", "--continue", "-c", action="store_true", help="Continue if the checkout copy has uncommited changes.")
    parser.add_argument("--force", "-f", action="store_true", help="Use force push, when pushing tags. This is needed relocate an existing tag to new commit (HEAD).")
    parser.add_argument("--no-op", "--noop", "-n", action="store_true", help="Run without making any changes. Just print out the git commands that would have been executed.")
    parser.add_argument("--tag-name-fmt", "-t", metavar="FMT", help="Custom format string that may contain {repo}, {repo_md5}, {tag} placeholders. Default env variable GIT_TAG_SUB_FMT or '"+parser.def_fmt.replace('%', '%%') + "'", default=parser.def_fmt)
    parser.add_argument("--modules", "-m", metavar="MODPAT", help="Limit to the listed submodules. The list is comma-seperated and supports glob patterns. Default: all aka '"+parser.def_mod.replace('%', '%%') + "'", default=parser.def_mod)
    parser.add_argument("tag", metavar="TAG", nargs="?", help="New tag to add and push everywhere. Default: look up and propagate existing tag(s) from current commit (HEAD).")
    args = parser.parse_args()
    if args.sametag: args.tag_name_fmt = '{tag}'
    if not args.quiet: verbose=True

    # print(args)

    topdir = git("rev-parse", "--show-toplevel")
    if topdir[-1] != '/':
        # assert that topdir has a trailing slash
        topdir = topdir + '/'
    submodules = git("submodule", "--quiet", "foreach", "--recursive", "pwd -P")    # oops, "$sm_path" is unreliable with --recursive
    if not submodules:
        print("ERROR: There are no submodules here.\n\t Maybe try changing to a parent repository?")
        sys.exit(1)
    submodules = glob_filter(submodules.splitlines(), args.modules.split(','))
    if not submodules:
        print("ERROR: Filtering with --modules matched nothing.\n\t Please check your glob patterns.")
        sys.exit(1)

    if not all(p.startswith(topdir) for p in submodules):
        raise ValueError("ERROR: assertion failed: submodules must be within topdir="+topdir+": "+str(submodules))
    submodules = [mod[len(topdir):] for mod in submodules]
    os.chdir(topdir)

    check_result = sanity_check(submodules)
    if check_result:
        if args.unclean:
            print("WARN: continuing unclean..")
        else:
            sys.exit(check_result)
    else:
        if verbose:
            print("Everything is clean, good ...\n")

    tags = []
    if args.tag:
        ## FIXME: do we need to check again? sanity_check() already did that...
        # if len(git("diff-index", "--numstat", "HEAD")) and not args.unclean:
        #     print("\nERROR: you have uncommited changes.\n\t When specifying new tags on the command line, we need this repo in a clean state.\n\t Specify option --unclean to continue (or commit your changes).")
        #     sys.exit(1)
        git("tag", "--force", args.tag, no_op=args.no_op)
        git_push_tags = [ "push", "--tags" ]
        if args.force:
            git_push_tags.append("--force")
        git(git_push_tags, no_op=args.no_op)
        tags.append(args.tag)
    else:
        r = git("tag", "--points-at", "HEAD")
        tags = r.split()

    ## FIXME: do we need to check again? sanity_check() already did that...
    # for mod in submodules:
    #     if len(git("diff-index", "--numstat", "HEAD", chdir=mod)) and not args.unclean:
    #         print(f"\nERROR: {mod}: submodule has uncommited changes.\n\t Specify option --unclean to continue (or commit your changes).")
    #         sys.exit(1)

    if not tags:
        print("ERROR: No tags found at the current commit (HEAD).\n\t Please specify one on the command line, or manually add one before retrying.\n\t If you want to move an existing tag, specify it on the command line with --force")
        sys.exit(1)

    for mod in submodules:
        for tag in tags:
            stag = args.tag_name_fmt.format(repo=repo_name, tag=tag, repo_md5=repo_md5)
            git("tag", "--force", stag, chdir=mod, no_op=args.no_op)
            git_push_tags = [ "push", "--tags" ]
            if args.force:
                git_push_tags.append("--force")
            git(git_push_tags, chdir=mod, no_op=args.no_op)

    sys.exit(check_result)


if __name__ == "__main__":
    main()
