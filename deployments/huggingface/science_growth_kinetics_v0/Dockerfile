# syntax=docker/dockerfile:1.7

FROM python:3.12-slim-bookworm AS builder

RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY requirements.lock /build/requirements.lock

RUN git init --initial-branch=main api-gym \
    && git -C api-gym remote add origin https://github.com/Oshawott324/datalox-api-gym.git \
    && git -C api-gym sparse-checkout init --cone \
    && git -C api-gym sparse-checkout set \
      api_gym \
      worlds/science_growth_kinetics_v0 \
    && git -C api-gym fetch \
      --depth=1 \
      --filter=blob:none \
      origin ca47eb299ae1ea9f96848807c3d74395d486cce4 \
    && git -C api-gym checkout --detach FETCH_HEAD \
    && test "$(git -C api-gym rev-parse HEAD)" = "ca47eb299ae1ea9f96848807c3d74395d486cce4"

RUN python -m pip install --no-cache-dir --upgrade pip wheel \
    && python -m pip wheel \
      --wheel-dir /wheels \
      --requirement /build/requirements.lock \
    && python -m pip wheel \
      --wheel-dir /wheels \
      --no-deps \
      ./api-gym

FROM python:3.12-slim-bookworm AS runtime

LABEL org.opencontainers.image.title="Datalox Science Growth Kinetics Space" \
      org.opencontainers.image.source="https://github.com/Oshawott324/datalox-api-gym" \
      io.datalox.api-gym.revision="ca47eb299ae1ea9f96848807c3d74395d486cce4" \
      io.datalox.gated-runtime.revision="ce5372623ddbab41dab169e4e0d0fc1c000a56c2"

RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates git \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 user \
    && mkdir -p /home/user/app /home/user/runs /opt/datalox/worlds \
    && chown user:user /home/user/app /home/user/runs

COPY --from=builder --chown=user:user \
  /build/api-gym/worlds/science_growth_kinetics_v0 \
  /opt/datalox/worlds/science_growth_kinetics_v0
COPY --from=builder --chown=user:user /wheels /tmp/wheels
COPY --from=builder --chown=user:user /build/requirements.lock /tmp/requirements.lock

USER user
WORKDIR /home/user/app

ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    DATALOX_GATE_EXAMPLES_DIR=/opt/datalox/worlds \
    DATALOX_RUNS_ROOT=/home/user/runs \
    DATALOX_ALLOWED_HOSTS="localhost:*,127.0.0.1:*" \
    DATALOX_ALLOWED_ORIGINS="" \
    DATALOX_MAX_SESSIONS=4 \
    DATALOX_SESSION_TTL_SECONDS=1800 \
    DATALOX_CLEANUP_INTERVAL_SECONDS=5

RUN python -m pip install \
      --user \
      --no-cache-dir \
      --no-index \
      --find-links=/tmp/wheels \
      --requirement /tmp/requirements.lock \
      datalox-api-gym==0.0.0 \
    && rm -rf /tmp/wheels /tmp/requirements.lock \
    && loaded=0 \
    && for attempt in 1 2 3; do \
      if python -c "from pylabrobot.resources.opentrons import opentrons_96_tiprack_300ul; opentrons_96_tiprack_300ul('build_cache')"; then \
        loaded=1; \
        break; \
      fi; \
      sleep "$((attempt * 2))"; \
    done \
    && test "${loaded}" = 1 \
    && printf '%s  %s\n' \
      afcaf30f86c3112b40246677d9f4dbef20bef938e0f65b8835195f448e058fd8 \
      /tmp/opentrons_96_tiprack_300ul.json \
      | sha256sum --check -

COPY --chown=user:user app.py entrypoint.sh /home/user/app/
COPY --chown=user:user scripts/run_reference.py /home/user/app/scripts/run_reference.py

RUN chmod 0755 /home/user/app/entrypoint.sh

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7860/health', timeout=4).read()" || exit 1

ENTRYPOINT ["/home/user/app/entrypoint.sh"]
