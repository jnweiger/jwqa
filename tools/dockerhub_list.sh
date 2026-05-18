#! /bin/sh

dockerhub_list()
{
    img_or_repo="$1"
    if [ -z "$img_or_repo" ]; then
        echo "Usage: $0 opencloudeu[/opencloud-rolling]"
        exit 0
    fi
    case "$img_or_repo" in
      */*) img_or_repo="$img_or_repo/tags" ;;
    esac
    curl -s "https://registry.hub.docker.com/v2/repositories/$img_or_repo?page_size=100&page=1" | jq -r .results.[].name
}

dockerhub_list "$1"
