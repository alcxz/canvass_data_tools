#!/usr/bin/env bash
#
# Deploy the backend to Lambda WITHOUT S3 and WITHOUT CloudFormation.
#
# `aws lambda update-function-code --zip-file` uploads the package straight to
# Lambda (50MB zipped limit), so no deployment artifact is ever stored in S3 and
# nothing accrues storage charges.
#
# The trade, accepted deliberately: CloudFormation does not manage this function,
# so there is no automatic rollback and no stack to describe. Rolling back means
# re-running this script from an older commit. backend/template.yaml is kept as
# documentation of the intended infrastructure but is NOT the deploy path --
# running `sam deploy` would create a second, separate function.
#
# Dependencies are fetched as prebuilt manylinux aarch64 wheels rather than
# compiled locally, so this works on an Apple Silicon Mac with no Docker and no
# `sam build`.
#
# Configuration comes from the gitignored .env, so no secret is ever typed on the
# command line where it would land in shell history.
#
# Usage:
#   ./scripts/deploy_backend.sh          # build and deploy code
#   ./scripts/deploy_backend.sh --env    # also push environment variables
#   ./scripts/deploy_backend.sh --url    # print the Function URL and exit

set -euo pipefail

FUNCTION_NAME="${FUNCTION_NAME:-ward11-canvass-api}"
ROLE_NAME="${ROLE_NAME:-${FUNCTION_NAME}-role}"
REGION="${AWS_REGION:-ca-central-1}"
RUNTIME="python3.12"
ARCH="arm64"
PLATFORM="manylinux2014_aarch64"
LOG_RETENTION_DAYS=7

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="$REPO_ROOT/.build/backend"
ZIP_PATH="$REPO_ROOT/.build/function.zip"

cd "$REPO_ROOT"

url_only=false
push_env=false
for arg in "$@"; do
    case "$arg" in
        --url) url_only=true ;;
        --env) push_env=true ;;
        *) echo "unknown option: $arg" >&2; exit 2 ;;
    esac
done

print_url() {
    aws lambda get-function-url-config \
        --function-name "$FUNCTION_NAME" --region "$REGION" \
        --query FunctionUrl --output text
}

# So no 403 errors.
ensure_url_permissions() {
    local out
    for stmt in \
        "FunctionURLAllowPublicAccess lambda:InvokeFunctionUrl --function-url-auth-type NONE" \
        "FunctionURLInvokeAllowPublicAccess lambda:InvokeFunction --invoked-via-function-url"
    do
        # shellcheck disable=SC2086  # word-splitting the flags is the point
        set -- $stmt
        if out=$(aws lambda add-permission \
                --function-name "$FUNCTION_NAME" \
                --statement-id "$1" --action "$2" --principal '*' "${@:3}" \
                --region "$REGION" --no-cli-pager 2>&1); then
            echo "  added permission $1"
        elif [[ "$out" != *ResourceConflictException* ]]; then
            echo "$out" >&2
            return 1
        fi
    done
}

if [[ "$url_only" == true ]]; then
    print_url
    exit 0
fi

# --- configuration ----------------------------------------------------------
if [[ -f .env ]]; then
    set -a; . ./.env; set +a
fi

# These three become the function's environment variables. They are NOT the
# frontend's VITE_ variables: SUPABASE_URL and VITE_SUPABASE_URL hold the same
# value but live in different places, because the browser bundle and the Lambda
# environment are separate deployment targets.
#   DATABASE_URL     -> backend/db.py, the Supavisor pooled connection string
#   SUPABASE_URL     -> backend/auth.py, to fetch the JWKS for JWT verification
#   ALLOWED_ORIGINS  -> backend/main.py, CORS
missing=()
for var in DATABASE_URL SUPABASE_URL ALLOWED_ORIGINS; do
    [[ -z "${!var:-}" ]] && missing+=("$var")
done
if (( ${#missing[@]} )); then
    echo "ERROR: missing from .env: ${missing[*]}" >&2
    echo "See .env.example." >&2
    exit 1
fi

if [[ "$DATABASE_URL" == *":5432"* ]]; then
    echo "WARNING: DATABASE_URL uses port 5432 (direct connection)." >&2
    echo "         Use the Supavisor pooled string on 6543 -- Lambda concurrency" >&2
    echo "         will exhaust direct connections." >&2
fi

env_json="$(python3 -c '
import json, os
print(json.dumps({"Variables": {
    "DATABASE_URL": os.environ["DATABASE_URL"],
    "SUPABASE_URL": os.environ["SUPABASE_URL"],
    "ALLOWED_ORIGINS": os.environ["ALLOWED_ORIGINS"],
}}))')"

# --- build ------------------------------------------------------------------
echo "building deployment package ..."
rm -rf "$BUILD_DIR" "$ZIP_PATH"
mkdir -p "$BUILD_DIR"

# --platform with --only-binary pulls Linux wheels regardless of the host OS.
# This is what removes the Docker requirement: nothing is compiled locally, the
# prebuilt aarch64 wheels for psycopg-binary and cryptography are just downloaded.
python3 -m pip install \
    --quiet --disable-pip-version-check \
    --platform "$PLATFORM" \
    --implementation cp \
    --python-version 3.12 \
    --only-binary=:all: \
    --target "$BUILD_DIR" \
    -r backend/requirements.txt

# Application code sits at the zip root so the handler resolves as main.handler.
# requirements*.txt and template.yaml are deliberately not copied.
cp backend/*.py "$BUILD_DIR/"

( cd "$BUILD_DIR" && zip -qr "$ZIP_PATH" . -x '*.pyc' -x '*__pycache__*' )

size_bytes=$(wc -c < "$ZIP_PATH")
printf '  package: %s MB\n' "$(( size_bytes / 1024 / 1024 ))"
if (( size_bytes >= 50 * 1024 * 1024 )); then
    echo "ERROR: direct upload is capped at 50MB zipped. Trim dependencies, or" >&2
    echo "       deploy via S3 instead." >&2
    exit 1
fi

# --- create on first run, update thereafter ---------------------------------
if aws lambda get-function --function-name "$FUNCTION_NAME" --region "$REGION" >/dev/null 2>&1; then
    echo "updating function code ..."
    aws lambda update-function-code \
        --function-name "$FUNCTION_NAME" \
        --zip-file "fileb://$ZIP_PATH" \
        --region "$REGION" \
        --no-cli-pager --query 'LastModified' --output text
    aws lambda wait function-updated --function-name "$FUNCTION_NAME" --region "$REGION"

    ensure_url_permissions

    if [[ "$push_env" == true ]]; then
        echo "updating environment variables ..."
        aws lambda update-function-configuration \
            --function-name "$FUNCTION_NAME" \
            --environment "$env_json" \
            --region "$REGION" \
            --no-cli-pager --query 'LastModified' --output text
        aws lambda wait function-updated --function-name "$FUNCTION_NAME" --region "$REGION"
    fi
else
    echo "function does not exist -- creating it ..."

    if ! aws iam get-role --role-name "$ROLE_NAME" >/dev/null 2>&1; then
        echo "  creating execution role $ROLE_NAME ..."
        aws iam create-role --role-name "$ROLE_NAME" \
            --assume-role-policy-document '{
                "Version": "2012-10-17",
                "Statement": [{
                    "Effect": "Allow",
                    "Principal": {"Service": "lambda.amazonaws.com"},
                    "Action": "sts:AssumeRole"
                }]
            }' --no-cli-pager >/dev/null
        # Grants only CloudWatch Logs write access. The function reaches Postgres
        # over the public internet with a password, not via IAM.
        aws iam attach-role-policy --role-name "$ROLE_NAME" \
            --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
        # IAM is eventually consistent. Creating the function immediately fails
        # with "The role defined for the function cannot be assumed by Lambda".
        echo "  waiting for the role to propagate ..."
        sleep 15
    fi

    role_arn="$(aws iam get-role --role-name "$ROLE_NAME" --query 'Role.Arn' --output text)"

    aws lambda create-function \
        --function-name "$FUNCTION_NAME" \
        --runtime "$RUNTIME" \
        --architectures "$ARCH" \
        --role "$role_arn" \
        --handler main.handler \
        --timeout 15 \
        --memory-size 512 \
        --description "Ward 11 canvass API" \
        --environment "$env_json" \
        --zip-file "fileb://$ZIP_PATH" \
        --region "$REGION" \
        --no-cli-pager --query 'FunctionArn' --output text
    aws lambda wait function-active --function-name "$FUNCTION_NAME" --region "$REGION"

    aws lambda create-function-url-config \
        --function-name "$FUNCTION_NAME" \
        --auth-type NONE \
        --region "$REGION" --no-cli-pager >/dev/null

    ensure_url_permissions

    # Lambda would otherwise create this log group with retention set to "never
    # expire", and stored logs then accrue indefinitely.
    aws logs create-log-group \
        --log-group-name "/aws/lambda/$FUNCTION_NAME" \
        --region "$REGION" >/dev/null 2>&1 || true
    aws logs put-retention-policy \
        --log-group-name "/aws/lambda/$FUNCTION_NAME" \
        --retention-in-days "$LOG_RETENTION_DAYS" \
        --region "$REGION"
fi

echo
echo "deployed. Function URL:"
print_url
echo
echo "Set that as VITE_API_URL in frontend/.env.local and in Vercel. VITE_ vars are"
echo "baked in at build time, so redeploy the frontend after changing it."
