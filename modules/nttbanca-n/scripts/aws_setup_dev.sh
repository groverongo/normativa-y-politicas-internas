#!/usr/bin/env bash
# Crea en AWS los recursos de desarrollo del backend y genera el .env:
#   1. Bucket S3 privado
#   2. Usuario IAM con permisos solo sobre ese bucket, y su access key
#   3. Security group con el puerto 5432 abierto solo para tu IP
#   4. Instancia RDS PostgreSQL con la base de la app
#   5. Archivo .env con todos los valores
#
# Se puede volver a correr: reutiliza lo que ya exista.
#
# Uso (en Windows, desde Git Bash):
#   bash scripts/aws_setup_dev.sh
#
# Variables opcionales:
#   AWS_REGION         región donde se crea todo        (us-east-1)
#   PROJECT            prefijo de los nombres           (nttbanca)
#   BUCKET             nombre del bucket                (<PROJECT>-dev-<cuenta>-<región>)
#   DB_PASSWORD        contraseña del usuario master    (aleatoria)
#   DB_INSTANCE_CLASS  tamaño de la instancia RDS       (db.t4g.micro)
#   MY_IP              IP a la que se abre el 5432      (tu IP pública actual)
#
# Ejemplo: AWS_REGION=sa-east-1 bash scripts/aws_setup_dev.sh

set -euo pipefail

cd "$(dirname "$0")/.."   # raíz del proyecto, donde va el .env

AWS_REGION="${AWS_REGION:-us-east-1}"
PROJECT="${PROJECT:-nttbanca}"
DB_INSTANCE_CLASS="${DB_INSTANCE_CLASS:-db.t4g.micro}"

IAM_USER="${PROJECT}-dev"
POLICY_NAME="${PROJECT}-s3-dev"
SG_NAME="${PROJECT}-rds-dev"
DB_INSTANCE_ID="${PROJECT}-dev"
DB_NAME="${PROJECT}"
DB_USER="${PROJECT}_admin"
POLICY_FILE=".aws-s3-policy.json"

export AWS_DEFAULT_REGION="$AWS_REGION"
export AWS_PAGER=""   # que el CLI no abra un paginador y bloquee el script

trap 'rm -f "$POLICY_FILE"' EXIT

step() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
info() { printf '    %s\n' "$*"; }
warn() { printf '\033[1;33m    ! %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31mError: %s\033[0m\n' "$*" >&2; exit 1; }

# En Git Bash el CLI de Windows devuelve CRLF: se quita el \r para poder usar los valores.
awsq() { aws "$@" --output text | tr -d '\r'; }


step "Verificando AWS CLI y credenciales"
command -v aws >/dev/null \
  || die "No se encontró 'aws'. Instala AWS CLI v2: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"
CALLER=$(awsq sts get-caller-identity --query '[Account,Arn]') \
  || die "El CLI no tiene credenciales válidas. Ejecuta 'aws configure' (o 'aws configure sso') y vuelve a intentar."
read -r ACCOUNT_ID CALLER_ARN <<< "$CALLER"
BUCKET="${BUCKET:-${PROJECT}-dev-${ACCOUNT_ID}-${AWS_REGION}}"
info "Cuenta:    $ACCOUNT_ID"
info "Identidad: $CALLER_ARN"
info "Región:    $AWS_REGION"


step "1/5 Bucket S3: $BUCKET"
if aws s3api head-bucket --bucket "$BUCKET" >/dev/null 2>&1; then
  info "Ya existe en tu cuenta; se reutiliza."
else
  if [ "$AWS_REGION" = "us-east-1" ]; then
    aws s3api create-bucket --bucket "$BUCKET" >/dev/null
  else
    aws s3api create-bucket --bucket "$BUCKET" \
      --create-bucket-configuration "LocationConstraint=$AWS_REGION" >/dev/null
  fi || die "No se pudo crear el bucket. Si el nombre ya lo usa otra cuenta, elige otro con BUCKET=..."
  info "Creado."
fi
aws s3api put-public-access-block --bucket "$BUCKET" \
  --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
info "Acceso público bloqueado."


step "2/5 Usuario IAM: $IAM_USER"
if aws iam get-user --user-name "$IAM_USER" >/dev/null 2>&1; then
  info "Ya existe; se reutiliza."
else
  aws iam create-user --user-name "$IAM_USER" >/dev/null
  info "Creado."
fi

cat > "$POLICY_FILE" <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ListarBucket",
      "Effect": "Allow",
      "Action": ["s3:ListBucket"],
      "Resource": "arn:aws:s3:::${BUCKET}"
    },
    {
      "Sid": "ObjetosDelBucket",
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
      "Resource": "arn:aws:s3:::${BUCKET}/*"
    }
  ]
}
EOF
aws iam put-user-policy --user-name "$IAM_USER" --policy-name "$POLICY_NAME" \
  --policy-document "file://$POLICY_FILE"
info "Política $POLICY_NAME aplicada (solo el bucket $BUCKET)."

# Ojo: no usar AWS_ACCESS_KEY_ID como nombre aquí; si estuviera exportada,
# cambiaría las credenciales del propio CLI en los pasos siguientes.
APP_KEY_ID=""
APP_KEY_SECRET=""
KEY_COUNT=$(awsq iam list-access-keys --user-name "$IAM_USER" --query 'length(AccessKeyMetadata)')
if [ "$KEY_COUNT" = "0" ]; then
  read -r APP_KEY_ID APP_KEY_SECRET < <(awsq iam create-access-key --user-name "$IAM_USER" \
    --query 'AccessKey.[AccessKeyId,SecretAccessKey]')
  [ -n "$APP_KEY_SECRET" ] || die "No se pudo crear la access key."
  info "Access key creada: $APP_KEY_ID"
else
  warn "El usuario ya tiene $KEY_COUNT access key(s) y el secret solo se ve al crearla, así que no va al .env."
  warn "Si la perdiste, bórrala y vuelve a correr el script:"
  warn "  aws iam list-access-keys --user-name $IAM_USER"
  warn "  aws iam delete-access-key --user-name $IAM_USER --access-key-id <AccessKeyId>"
fi


step "3/5 Security group: $SG_NAME"
VPC_ID=$(awsq ec2 describe-vpcs --filters Name=is-default,Values=true --query 'Vpcs[0].VpcId')
[ "$VPC_ID" != "None" ] \
  || die "La región $AWS_REGION no tiene VPC por defecto. Créala con: aws ec2 create-default-vpc"
SG_ID=$(awsq ec2 describe-security-groups \
  --filters "Name=group-name,Values=$SG_NAME" "Name=vpc-id,Values=$VPC_ID" \
  --query 'SecurityGroups[0].GroupId')
if [ "$SG_ID" = "None" ]; then
  SG_ID=$(awsq ec2 create-security-group --group-name "$SG_NAME" --vpc-id "$VPC_ID" \
    --description "PostgreSQL dev - acceso desde las IPs del equipo" --query GroupId)
  info "Creado: $SG_ID"
else
  info "Ya existe: $SG_ID"
fi

if [ -z "${MY_IP:-}" ]; then
  MY_IP=$(curl -fsS https://checkip.amazonaws.com | tr -d '\r\n ') \
    || die "No se pudo obtener tu IP pública. Pásala con MY_IP=x.x.x.x"
fi
if out=$(aws ec2 authorize-security-group-ingress --group-id "$SG_ID" \
    --protocol tcp --port 5432 --cidr "$MY_IP/32" 2>&1); then
  info "Puerto 5432 abierto para $MY_IP/32"
elif [[ "$out" == *InvalidPermission.Duplicate* ]]; then
  info "El puerto 5432 ya estaba abierto para $MY_IP/32"
else
  die "$out"
fi


step "4/5 RDS PostgreSQL: $DB_INSTANCE_ID"
if aws rds describe-db-instances --db-instance-identifier "$DB_INSTANCE_ID" >/dev/null 2>&1; then
  read -r DB_STATUS DB_NAME DB_USER < <(awsq rds describe-db-instances --db-instance-identifier "$DB_INSTANCE_ID" \
    --query 'DBInstances[0].[DBInstanceStatus,DBName,MasterUsername]')
  info "Ya existe (estado: $DB_STATUS); se reutiliza."
  if [ "$DB_STATUS" = "stopped" ]; then
    aws rds start-db-instance --db-instance-identifier "$DB_INSTANCE_ID" >/dev/null
    info "Estaba detenida; se está encendiendo."
  fi
  [ -n "${DB_PASSWORD:-}" ] \
    || warn "No se conoce la contraseña del master: complétala a mano en el .env (o vuelve a correr con DB_PASSWORD=...)."
else
  if [ -z "${DB_PASSWORD:-}" ]; then
    DB_PASSWORD=$(openssl rand -hex 16) || die "No se pudo generar la contraseña. Pásala con DB_PASSWORD=..."
  fi
  aws rds create-db-instance \
    --db-instance-identifier "$DB_INSTANCE_ID" \
    --engine postgres \
    --db-instance-class "$DB_INSTANCE_CLASS" \
    --allocated-storage 20 \
    --storage-type gp2 \
    --db-name "$DB_NAME" \
    --master-username "$DB_USER" \
    --master-user-password "$DB_PASSWORD" \
    --vpc-security-group-ids "$SG_ID" \
    --publicly-accessible \
    --backup-retention-period 1 \
    --no-multi-az \
    --no-deletion-protection \
    --tags "Key=Project,Value=$PROJECT" "Key=Environment,Value=dev" >/dev/null
  info "Creación iniciada."
fi

info "Esperando a que esté disponible (suele tardar 5-15 minutos)..."
aws rds wait db-instance-available --db-instance-identifier "$DB_INSTANCE_ID" \
  || die "Tardó más de lo esperado. Vuelve a correr el script: reutiliza lo ya creado."
DB_HOST=$(awsq rds describe-db-instances --db-instance-identifier "$DB_INSTANCE_ID" \
  --query 'DBInstances[0].Endpoint.Address')
info "Endpoint: $DB_HOST"


step "5/5 Archivo .env"
ENV_FILE=".env"
if [ -e "$ENV_FILE" ]; then
  ENV_FILE=".env.aws-dev"
  warn "Ya existe un .env y no se toca. Los valores van a $ENV_FILE: revísalo y cópialo a .env."
fi
cat > "$ENV_FILE" <<EOF
# Generado por scripts/aws_setup_dev.sh el $(date '+%Y-%m-%d %H:%M')
APP_NAME=NttBanca API
DEBUG=true

DB_HOST=$DB_HOST
DB_PORT=5432
DB_NAME=$DB_NAME
DB_USER=$DB_USER
DB_PASSWORD='${DB_PASSWORD:-}'
DB_SSLMODE=require
DB_CONNECT_TIMEOUT=10
DB_AUTO_CREATE_TABLES=true

AWS_REGION=$AWS_REGION
AWS_ACCESS_KEY_ID=$APP_KEY_ID
AWS_SECRET_ACCESS_KEY=$APP_KEY_SECRET
AWS_SESSION_TOKEN=
S3_BUCKET_NAME=$BUCKET
S3_KEY_PREFIX=uploads
S3_PRESIGNED_URL_EXPIRATION=3600
EOF
info "Escrito: $ENV_FILE"


step "Listo"
cat <<EOF
    Bucket S3       $BUCKET
    Usuario IAM     $IAM_USER
    Security group  $SG_ID  (5432 abierto para $MY_IP/32)
    RDS             $DB_HOST
                    base: $DB_NAME   usuario: $DB_USER

    Siguiente paso (en PowerShell):
      .\\.venv\\Scripts\\Activate.ps1
      fastapi dev app/main.py

    Y abre http://127.0.0.1:8000/health/db y http://127.0.0.1:8000/health/s3
    (una access key recién creada puede tardar unos segundos en funcionar).

    Si tu IP cambia, vuelve a correr el script para abrir el puerto a la nueva.
EOF
