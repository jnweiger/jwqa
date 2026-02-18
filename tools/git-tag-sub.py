#! /usr/bin/python3
#
# find all tags at the current commit of this repo.
# per default prefix the name of the current repo with / to the tag to generate the tag name for submodules
# if --no-prefix or --same is given, then tag-name-fmt is set to '%s'. --tag-name-fmt defaults to 'reponame/%s'
# where reponame is derived from the current toplevel repo.
# iterate through all submodules with foreach, push the tag after applyig the format
# warn for each git repo, if there are uncommited changes. (unless --unclean option is specified)
#
# we definitly error out, when there is a dirty submodule. when git diff shows you something like
# --- a/src/test-sub2mod
# +++ b/src/test-sub2mod
# @@ -1 +1 @@
# -Subproject commit 012a120db7d601347271da4b9148e925c240d6d3
# +Subproject commit 012a120db7d601347271da4b9148e925c240d6d3-dirty
#
# then you have to "git add src/test-sub2mod; git commit" to get things in sync.
# there is a built in sanity check, that will always complain about the above.
# With --check-only we do the up front sanity checks, wihtout propagating any tags.


import sys, os, argparse, subprocess
from pathlib import Path

__VERSION__ = '0.2'
verbose = False


def git(*args, no_op=False):
    """Run a git command and return its stdout stripped."""
    if type(args) == type(()) and type(args[0]) == type([]):
        # accept mutiple strings or a single list.
        args = args[0]

    if verbose:
        if no_op:
            print("# ", eol='')
        print("+ git " + ' '.join(args))

    if no_op:
        return ''

    result = subprocess.run(["git"] + list(args), stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, check=False)
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


def sanity_check():
    # start with sanity checks.
    # 
    # 0       0       LICENSE => LICENSE.md
    # 0       1       bar
    # 0       0       src/second-best/test-sub2mod
    topdir=git("rev-parse", "--show-toplevel")
    main_numstat = git("diff-index", "--numstat", "HEAD")
    # task: CD to the topdir, then check all the lines from main_numstat that start with any two digits, and if the remaining path contains a file(!) '.git' sub.
    # if so, we found a dirty submodule.
    # FIXME: do we need to do this recursive?
    dirty = []
    for line in main_numstat.split("\n"):
        words=line.split()
        # print("checking: ", topdir + '/' + words[2] + "/.git")
        if len(words) == 3 and os.path.isfile(topdir + '/' + words[2] + "/.git"):
            dirty.append(words[2])
            print("ERROR: sanity check failed: submodule not clean: ", words[2])
    if dirty:
        if len(git("submodule", "--quiet", "foreach", "--recursive", "git diff-index --numstat HEAD | sed -e \"s@^@$sm_path: @\"")):
            print("\nERROR: you have uncommited changes in one or more submodules.\n\t Everything must be cleanly committed or stashed before we can propagate tags.")
        return len(dirty)
    return 0


def main():
    global verbose

    try:
        repo_name = git_repo_name()
    except:
        repo_name = 'REPO'

    parser = argparse.ArgumentParser(allow_abbrev=False, epilog="version: "+__VERSION__, description="Propagate git tags into submodules.")
    parser.def_fmt = repo_name + "/%s"

    parser.add_argument("--no-prefix", "--same", action="store_true", help="Do not prefix tags with the repository name.")
    parser.add_argument("--quiet", "-q", action="store_true", help="Print git commands.")
    parser.add_argument("--unclean", "--continue", "-c", action="store_true", help="Continue if the checkout copy has uncommited changes.")
    parser.add_argument("--force", action="store_true", help="Use force push, when pushing tags. This is needed relocate an existing tag to new commit (HEAD).")
    parser.add_argument("--check-only", action="store_true", help="Just do sanity checks. No tags are propagated into submodules.")
    parser.add_argument("--no-op", action="store_true", help="Run without making any changes. Just print out the git commands that would have been executed.")
    parser.add_argument("--tag-name-fmt", metavar="FMT", help="Custom format string containing a single %%s placeholder. Default (derived from the current repo): '"+parser.def_fmt.replace('%', '%%') + "'", default=parser.def_fmt)
    parser.add_argument("tag", metavar="TAG", nargs="?", help="New tag to add and push everywhere. Default: look up and propagate existing tag(s) from current commit (HEAD).")
    args = parser.parse_args()
    if args.no_prefix: args.tag_name_fmt = '%s'
    if not args.quiet: verbose=True

    # print(args)

    r = sanity_check()
    if r or args.check_only:
        sys.exit(r)

    tags = []
    if args.tag:
        if len(git("diff-index", "--numstat", "HEAD")) and not args.unclean:
            print("\nERROR: you have uncommited changes.\n\t Specify option --unclean to continue (or commit your changes).")
            sys.exit(1)
        git("tag", "--force", args.tag, no_op=args.no_op)
        git_push_tags = [ "push", "--tags" ]
        if args.force:
            git_push_tags.append("--force")
        git(git_push_tags, no_op=args.no_op)
        tags.append(args.tag)
    else:
        r = git("tag", "--points-at", "HEAD")
        tags = r.split()

    if len(git("submodule", "--quiet", "foreach", "--recursive", "git diff-index --numstat HEAD | sed -e \"s@^@$sm_path: @\"")) and not args.unclean:
        print("\nERROR: you have uncommited changes in one or more submodules.\n\t Specify option --unclean to continue (or commit your changes).")
        sys.exit(1)
    
    if not tags:
        print("ERROR: No tags found at the current commit (HEAD).\n\t Please specify one on the command line, or manually add one before retrying.\n\t If you want to move an existing tag, specify it on the command line with --force")
        sys.exit(1)
        
    for tag in tags:
        stag = args.tag_name_fmt % tag
        git("submodule", "--quiet", "foreach", "--recursive", "git", "tag", "--force", stag, no_op=args.no_op)
        git_push_tags = [ "submodule", "--quiet", "foreach", "--recursive", "git", "push", "--tags" ]
        if args.force:
            git_push_tags.append("--force")
        git(git_push_tags, no_op=args.no_op)
        





if __name__ == "__main__":
    main()
