###########################
# ---- Builder Stage ---- #
###########################
FROM mcr.microsoft.com/playwright/python:v1.55.0-noble AS builder

WORKDIR /project

# Install the uv tool for Python package management.
COPY --from=docker.io/astral/uv:latest /uv /uvx /bin/

# Set env vars for uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
# ENV PATH="/root/.local/bin:$PATH"

# Copy dependency definition files
COPY pyproject.toml uv.lock ./

# Create a virtual environment and install dependencies
# The uv cache is mounted to speed up subsequent builds.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-install-project --no-dev

# Copy the rest of the application source code
COPY . .

# Install the project itself using the frozen lock file
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

#########################
# ---- Final Stage ---- #
#########################
FROM mcr.microsoft.com/playwright/python:v1.55.0-noble AS runtime

WORKDIR /project

ENV PYTHONUNBUFFERED=1

# Create a non-root user and group
# The Playwright image has 'pwuser' (UID 1000), ensure /project is owned by pwuser.
RUN chown -R 1000:1000 /project

# Copy application files including virtual environment from the builder stage
COPY --from=builder --chown=1000:1000 /project .

# Add the virtual environment's bin directory to the PATH
ENV PATH="/project/.venv/bin:$PATH"

# Make the entrypoint script executable
RUN chmod +x ./entrypoint.sh

# Switch to the non-root user
USER 1000

EXPOSE 8000

# Health check (assuming you add a /healthz endpoint to your FastAPI app)
HEALTHCHECK --interval=60s --timeout=10s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8000/healthz || exit 1

# Set the container's entrypoint
ENTRYPOINT ["./entrypoint.sh"]
