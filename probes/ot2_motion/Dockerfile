FROM python:3.12-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp
WORKDIR /workspace
COPY probes/ot2_motion/requirements.lock /opt/requirements.lock
RUN python -m pip install --no-cache-dir --only-binary=:all: --require-hashes -r /opt/requirements.lock
COPY api_gym/__init__.py /workspace/api_gym/__init__.py
COPY api_gym/source_packs.py /workspace/api_gym/source_packs.py
COPY api_gym/instrument_models /workspace/api_gym/instrument_models
COPY probes/ot2_motion /workspace/probes/ot2_motion
COPY tests/instrument_models /workspace/tests/instrument_models
USER 65534:65534
CMD ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/instrument_models"]
