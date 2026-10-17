# Configurar S3 y RDS para desarrollo

Guía para crear en AWS el bucket de S3 y la base PostgreSQL que usa el backend, y dejarlo corriendo en tu
máquina contra esos recursos.

> Esta configuración es para **desarrollo y pruebas**: la base es accesible desde internet (solo desde tu
> IP) y se usan access keys de un usuario IAM. En producción la base debe ser privada y la API debe usar un
> rol IAM (ver [Cuando lo despliegues](#cuando-lo-despliegues)).

## Opción rápida: script por terminal

[`scripts/aws_setup_dev.sh`](../scripts/aws_setup_dev.sh) hace los pasos 3, 4, 5 y 6 de esta guía con el AWS CLI y
genera el `.env`. Requisito: AWS CLI v2 configurada con un usuario administrador (`aws configure`).

En Windows, desde **Git Bash** y en la raíz del proyecto:

```bash
aws sts get-caller-identity          # comprueba que el CLI tiene credenciales
bash scripts/aws_setup_dev.sh        # o: AWS_REGION=sa-east-1 bash scripts/aws_setup_dev.sh
```

- Crea el bucket `nttbanca-dev-<cuenta>-<región>`, el usuario IAM `nttbanca-dev` con su access key, el security
  group `nttbanca-rds-dev` (5432 abierto solo para tu IP) y la instancia RDS `nttbanca-dev` con la base `nttbanca`.
- Espera a que RDS esté disponible (5-15 minutos) y escribe el `.env`. Si ya tienes uno, no lo toca y escribe
  `.env.aws-dev`.
- Se puede volver a correr: reutiliza lo que ya existe. Sirve, por ejemplo, para abrir el puerto a tu IP nueva
  cuando cambia. En una segunda corrida no puede recuperar el secret de la access key ni la contraseña de la
  base; te avisa para que los completes a mano.

Después sigue en el [paso 7](#7-levantar-el-backend-y-probarlo). El resto de esta guía explica lo mismo paso a
paso, por si prefieres la consola web o necesitas ajustar algo.

## Índice

1. [Lo que vas a crear](#1-lo-que-vas-a-crear)
2. [Requisitos](#2-requisitos)
3. [Bucket de S3](#3-bucket-de-s3)
4. [Usuario IAM para la API](#4-usuario-iam-para-la-api)
5. [Base de datos en RDS](#5-base-de-datos-en-rds)
6. [Configurar el `.env`](#6-configurar-el-env)
7. [Levantar el backend y probarlo](#7-levantar-el-backend-y-probarlo)
8. [Problemas frecuentes](#8-problemas-frecuentes)
9. [Costos, apagar y borrar](#9-costos-apagar-y-borrar)
10. [Cuando lo despliegues](#cuando-lo-despliegues)

---

## 1. Lo que vas a crear

```
 Tu PC                                   AWS (una sola región, p. ej. us-east-1)
┌──────────────────────┐                ┌─────────────────────────────────────────────┐
│  FastAPI             │  access keys   │  S3 bucket  nttbanca-dev-<algo-único>       │
│  (fastapi dev)       │ ─────────────► │    └── uploads/<uuid>.<ext>                 │
│                      │                │                                             │
│  .env                │  TCP 5432+SSL  │  RDS PostgreSQL  nttbanca-dev               │
│                      │ ─────────────► │    └── base nttbanca  → tablas items, files │
└──────────────────────┘  (solo tu IP)  │        (security group: 5432 desde tu IP)   │
                                        └─────────────────────────────────────────────┘
```

| Recurso          | Nombre sugerido                 | Para qué                                     |
|------------------|---------------------------------|----------------------------------------------|
| Bucket S3        | `nttbanca-dev-<algo-único>`     | Guardar los archivos                         |
| Usuario IAM      | `nttbanca-dev`                  | Credenciales de la API para usar el bucket   |
| Security group   | `nttbanca-rds-dev`              | Permitir el puerto 5432 solo desde tu IP     |
| Instancia RDS    | `nttbanca-dev`                  | PostgreSQL                                   |
| Base de datos    | `nttbanca`                      | Donde la API crea las tablas `items` y `files` |

Usa **la misma región** para todo y anótala; va en `AWS_REGION`.

## 2. Requisitos

- Una cuenta de AWS y un usuario con permisos de administrador (o al menos sobre S3, IAM, RDS y EC2).
  No uses la cuenta root.
- El backend instalado (ver [README](../README.md#puesta-en-marcha)).
- Opcional, para los pasos por CLI: [AWS CLI v2](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)
  configurada con `aws configure` (o `aws configure sso`). Comprueba que funciona con:

  ```bash
  aws sts get-caller-identity
  ```

- Opcional, para entrar a la base con SQL: `psql` (viene con el instalador de PostgreSQL), DBeaver o pgAdmin.

Cada paso tiene instrucciones de **consola** y, desplegable, la alternativa por **CLI**. Los comandos CLI
están en bash: en Windows ejecútalos en Git Bash. Antes de usarlos define estas variables:

```bash
export AWS_REGION=us-east-1
export BUCKET=nttbanca-dev-$RANDOM$RANDOM      # debe ser único en todo S3
export DB_PASSWORD='CambiaEsto-123'            # sin / " @ ni espacios (restricción de RDS)
echo "Bucket: $BUCKET"
```

---

## 3. Bucket de S3

### Consola

1. Entra a **S3 → Create bucket**.
2. **Bucket type**: General purpose.
3. **Bucket name**: `nttbanca-dev-<algo-único>`, en minúsculas, con números y guiones. Debe ser único en todo
   AWS, no solo en tu cuenta.
4. **AWS Region**: la región que elegiste.
5. **Object Ownership**: ACLs disabled (valor por defecto).
6. **Block all public access**: déjalo **activado**. La API sirve los archivos con descarga propia o con URLs
   firmadas, así que el bucket nunca necesita ser público.
7. **Bucket Versioning**: Disable. En desarrollo no hace falta, y con versionado los archivos borrados siguen
   ocupando espacio.
8. **Default encryption**: SSE-S3 (valor por defecto).
9. **Create bucket**.

<details>
<summary>CLI</summary>

```bash
# En us-east-1 no se pasa LocationConstraint; en cualquier otra región sí
if [ "$AWS_REGION" = "us-east-1" ]; then
  aws s3api create-bucket --bucket "$BUCKET" --region "$AWS_REGION"
else
  aws s3api create-bucket --bucket "$BUCKET" --region "$AWS_REGION" \
    --create-bucket-configuration LocationConstraint="$AWS_REGION"
fi

# Bloqueo de acceso público (ya viene activado en buckets nuevos; esto lo deja explícito)
aws s3api put-public-access-block --bucket "$BUCKET" \
  --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
```

</details>

### CORS (solo si hay un frontend)

Si un frontend en el navegador va a hacer `fetch` a las URLs firmadas (`/files/{id}/presigned-url`), el bucket
necesita CORS. Con un simple link `<a href>` o descargando por `/files/{id}/download` no hace falta.

**S3 → tu bucket → Permissions → Cross-origin resource sharing (CORS) → Edit**:

```json
[
  {
    "AllowedOrigins": ["http://localhost:3000", "http://localhost:5173"],
    "AllowedMethods": ["GET"],
    "AllowedHeaders": ["*"],
    "MaxAgeSeconds": 3000
  }
]
```

---

## 4. Usuario IAM para la API

La API necesita credenciales que solo puedan usar **este bucket**. No uses las de tu usuario administrador.

### Consola

1. **IAM → Users → Create user** → nombre `nttbanca-dev` → **sin** acceso a la consola → siguiente.
2. **Permissions options**: no agregues ninguna política todavía → **Create user**.
3. Abre el usuario → **Permissions → Add permissions → Create inline policy → JSON** y pega lo siguiente,
   reemplazando `NOMBRE-DEL-BUCKET` en las dos líneas:

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Sid": "ListarBucket",
         "Effect": "Allow",
         "Action": ["s3:ListBucket"],
         "Resource": "arn:aws:s3:::NOMBRE-DEL-BUCKET"
       },
       {
         "Sid": "ObjetosDelBucket",
         "Effect": "Allow",
         "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
         "Resource": "arn:aws:s3:::NOMBRE-DEL-BUCKET/*"
       }
     ]
   }
   ```

   Nombre de la política: `nttbanca-s3-dev` → **Create policy**.
4. En el mismo usuario: **Security credentials → Create access key → Local code** → **Create access key**.
5. Copia el **Access key ID** y el **Secret access key**. El secret se muestra **una sola vez**.

Qué usa cada permiso: `ListBucket` para `/health/s3`, `PutObject` para subir y reemplazar, `GetObject` para
descargar y para las URLs firmadas, y `DeleteObject` para borrar.

<details>
<summary>CLI</summary>

```bash
aws iam create-user --user-name nttbanca-dev

cat > s3-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    { "Sid": "ListarBucket", "Effect": "Allow", "Action": ["s3:ListBucket"],
      "Resource": "arn:aws:s3:::${BUCKET}" },
    { "Sid": "ObjetosDelBucket", "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
      "Resource": "arn:aws:s3:::${BUCKET}/*" }
  ]
}
EOF

aws iam put-user-policy --user-name nttbanca-dev \
  --policy-name nttbanca-s3-dev --policy-document file://s3-policy.json
rm s3-policy.json

# Muestra AccessKeyId y SecretAccessKey: cópialos al .env, no se vuelven a mostrar
aws iam create-access-key --user-name nttbanca-dev
```

</details>

> **¿Usas AWS SSO o perfiles?** Deja `AWS_ACCESS_KEY_ID` y `AWS_SECRET_ACCESS_KEY` vacíos en el `.env` y,
> antes de levantar la API, exporta el perfil en la terminal: `export AWS_PROFILE=mi-perfil` (bash) o
> `$env:AWS_PROFILE="mi-perfil"` (PowerShell). boto3 lo toma de ahí. En ese caso el permiso lo da el rol
> de tu perfil, no el usuario `nttbanca-dev`.

---

## 5. Base de datos en RDS

### 5.1 Crear la instancia (consola)

**RDS → Databases → Create database**:

| Sección                    | Valor                                                                    |
|----------------------------|--------------------------------------------------------------------------|
| Creation method            | **Standard create**. Easy create no deja activar el acceso público.      |
| Engine                     | PostgreSQL, con la versión por defecto                                   |
| Templates                  | **Free tier** (o Dev/Test si tu cuenta no lo muestra)                    |
| DB instance identifier     | `nttbanca-dev`                                                           |
| Master username            | `nttbanca_admin`                                                         |
| Credentials management     | **Self managed**, con una contraseña propia. Con *Managed in Secrets Manager* la contraseña rota sola y el `.env` quedaría desactualizado. |
| Master password            | Sin `/`, `"`, `@` ni espacios                                            |
| Instance class             | `db.t4g.micro`                                                           |
| Storage                    | **gp2**, 20 GiB, sin autoscaling. La capa gratuita cubre gp2, no gp3; la consola a veces propone gp3 por defecto. |
| Compute resource           | Don't connect to an EC2 compute resource                                 |
| VPC                        | Default VPC                                                              |
| **Public access**          | **Yes**. Sin esto no puedes conectarte desde tu PC.                      |
| VPC security group         | **Create new** → `nttbanca-rds-dev`                                      |
| Database authentication    | Password authentication                                                  |
| Monitoring                 | Desactiva Performance Insights y Enhanced Monitoring (costo extra)       |
| **Additional configuration → Initial database name** | **`nttbanca`**. Si lo dejas vacío, la base no se crea. |
| Backup retention           | 1 día                                                                    |
| Deletion protection        | Desactivado (es desarrollo)                                              |

**Create database**. Tarda entre 5 y 15 minutos hasta quedar en estado **Available**.

### 5.2 Abrir el puerto 5432 solo para tu IP

1. Abre la instancia → **Connectivity & security** → clic en el security group `nttbanca-rds-dev`.
2. **Inbound rules → Edit inbound rules**. Debe quedar una regla:
   - Type: **PostgreSQL** (TCP 5432)
   - Source: **My IP**
3. **Save rules**.

Si otra persona del equipo necesita conectarse, agrega una regla por cada IP. Si tu IP de casa cambia, actualiza
la regla (síntoma: `/health/db` da timeout). **Nunca uses `0.0.0.0/0`.**

### 5.3 Copiar el endpoint

En **Connectivity & security** copia el **Endpoint**, algo como
`nttbanca-dev.abc123xyz.us-east-1.rds.amazonaws.com`. Va en `DB_HOST`.

<details>
<summary>CLI (5.1, 5.2 y 5.3)</summary>

```bash
# Security group en la VPC por defecto con 5432 abierto solo para tu IP
VPC_ID=$(aws ec2 describe-vpcs --filters Name=is-default,Values=true \
  --query "Vpcs[0].VpcId" --output text)
SG_ID=$(aws ec2 create-security-group --group-name nttbanca-rds-dev \
  --description "Postgres dev - acceso desde IPs del equipo" --vpc-id "$VPC_ID" \
  --query GroupId --output text)
MY_IP=$(curl -s https://checkip.amazonaws.com)
aws ec2 authorize-security-group-ingress --group-id "$SG_ID" \
  --protocol tcp --port 5432 --cidr "${MY_IP}/32"

# Instancia PostgreSQL
aws rds create-db-instance \
  --db-instance-identifier nttbanca-dev \
  --engine postgres \
  --db-instance-class db.t4g.micro \
  --allocated-storage 20 \
  --storage-type gp2 \
  --db-name nttbanca \
  --master-username nttbanca_admin \
  --master-user-password "$DB_PASSWORD" \
  --vpc-security-group-ids "$SG_ID" \
  --publicly-accessible \
  --backup-retention-period 1 \
  --no-multi-az \
  --no-deletion-protection

# Espera a que esté disponible (5-15 min) y muestra el endpoint
aws rds wait db-instance-available --db-instance-identifier nttbanca-dev
aws rds describe-db-instances --db-instance-identifier nttbanca-dev \
  --query "DBInstances[0].Endpoint.Address" --output text
```

Para agregar la IP de otra persona más adelante:

```bash
aws ec2 authorize-security-group-ingress --group-id "$SG_ID" \
  --protocol tcp --port 5432 --cidr "IP.DE.LA.PERSONA/32"
```

</details>

### 5.4 (Opcional) Usuario propio para la API

Para empezar puedes usar el usuario master en el `.env`. Si la base la comparte el equipo, es mejor que la API
use un usuario sin privilegios de administrador. Conéctate como master (con psql, DBeaver o pgAdmin) a la base
`nttbanca` y ejecuta:

```sql
CREATE ROLE nttbanca_app WITH LOGIN PASSWORD 'OtraContrasena-456';
GRANT CONNECT ON DATABASE nttbanca TO nttbanca_app;
-- La API crea sus tablas al arrancar, así que necesita CREATE en el schema public
GRANT USAGE, CREATE ON SCHEMA public TO nttbanca_app;
```

Con psql:

```bash
psql "host=<ENDPOINT> port=5432 dbname=nttbanca user=nttbanca_admin sslmode=require"
```

Luego usa `nttbanca_app` y su contraseña en `DB_USER` y `DB_PASSWORD`.

---

## 6. Configurar el `.env`

En la raíz del proyecto:

```bash
cp .env.example .env
```

(En PowerShell: `copy .env.example .env`.) Completa los valores:

| Variable                | Valor de ejemplo                                         | De dónde sale                               |
|-------------------------|----------------------------------------------------------|---------------------------------------------|
| `DB_HOST`               | `nttbanca-dev.abc123xyz.us-east-1.rds.amazonaws.com`     | Paso 5.3, el endpoint                       |
| `DB_PORT`               | `5432`                                                   |                                             |
| `DB_NAME`               | `nttbanca`                                               | Initial database name (paso 5.1)            |
| `DB_USER`               | `nttbanca_admin` o `nttbanca_app`                        | Paso 5.1 o 5.4                              |
| `DB_PASSWORD`           | `'CambiaEsto-123'`                                       | Paso 5.1 o 5.4                              |
| `DB_SSLMODE`            | `require`                                                | RDS exige SSL; `require` basta en desarrollo |
| `AWS_REGION`            | `us-east-1`                                              | Región del bucket                           |
| `AWS_ACCESS_KEY_ID`     | `AKIA...`                                                | Paso 4                                      |
| `AWS_SECRET_ACCESS_KEY` | `...`                                                    | Paso 4                                      |
| `AWS_SESSION_TOKEN`     | *(vacío)*                                                | Solo con credenciales temporales            |
| `S3_BUCKET_NAME`        | `nttbanca-dev-123456789`                                 | Paso 3                                      |
| `S3_KEY_PREFIX`         | `uploads`                                                | Carpeta dentro del bucket                   |

Ejemplo completo:

```dotenv
APP_NAME=NttBanca API
DEBUG=true

DB_HOST=nttbanca-dev.abc123xyz.us-east-1.rds.amazonaws.com
DB_PORT=5432
DB_NAME=nttbanca
DB_USER=nttbanca_admin
DB_PASSWORD='CambiaEsto-123'
DB_SSLMODE=require
DB_CONNECT_TIMEOUT=10
DB_AUTO_CREATE_TABLES=true

AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=AKIAXXXXXXXXXXXXXXXX
AWS_SECRET_ACCESS_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
AWS_SESSION_TOKEN=
S3_BUCKET_NAME=nttbanca-dev-123456789
S3_KEY_PREFIX=uploads
S3_PRESIGNED_URL_EXPIRATION=3600
```

Notas:

- Pon la contraseña entre **comillas simples** si tiene `#`, `$` u otros símbolos. Así el `.env` no los
  interpreta como comentario o variable.
- El `.env` está en `.gitignore`. **No lo subas al repositorio** ni compartas las keys por chat; si se filtran,
  desactívalas en IAM y crea otras.
- Si varias personas comparten bucket pero cada una tiene su propia base, usen un `S3_KEY_PREFIX` distinto
  (por ejemplo `dev-ana`) para no mezclar archivos.

---

## 7. Levantar el backend y probarlo

```powershell
.\.venv\Scripts\Activate.ps1
fastapi dev app/main.py
```

En el log debe aparecer `Tablas verificadas/creadas en Postgres`. Si en su lugar sale
`No se pudo conectar a Postgres...`, la API igual arranca; revisa la [sección 8](#8-problemas-frecuentes).

### 7.1 Health checks

Abre en el navegador o con curl:

| URL                                 | Respuesta esperada                                         |
|-------------------------------------|------------------------------------------------------------|
| http://127.0.0.1:8000/health/db     | `{"status":"ok","service":"postgres"}`                     |
| http://127.0.0.1:8000/health/s3     | `{"status":"ok","service":"s3","bucket":"nttbanca-dev-…"}` |

Si alguno devuelve **503**, el `detail` dice qué falló.

### 7.2 Flujo completo

La forma más simple es **Swagger UI**, en http://127.0.0.1:8000/docs: ahí cada endpoint tiene **Try it out**,
incluso para subir archivos.

Con curl (Git Bash, macOS o Linux):

```bash
API=http://127.0.0.1:8000

# 1. Crear un item
curl -s -X POST $API/items -H "Content-Type: application/json" \
  -d '{"name": "Cliente demo", "description": "Prueba de integración"}'
# → {"id":1, ...}

# 2. Subir un archivo asociado al item 1
curl -s -X POST $API/files -F "file=@./contrato.pdf" -F "item_id=1"
# → {"id":1, "s3_key":"uploads/3f2a....pdf", "size_bytes":..., ...}

# 3. Consultar
curl -s $API/items/1/files
curl -s $API/files/1

# 4. Descargar por la API o pedir una URL firmada (ábrela en el navegador)
curl -s -o descargado.pdf $API/files/1/download
curl -s $API/files/1/presigned-url

# 5. Reemplazar el contenido y renombrar
curl -s -X PUT $API/files/1 -F "file=@./contrato_v2.pdf"
curl -s -X PATCH $API/files/1 -H "Content-Type: application/json" -d '{"original_filename": "contrato-firmado.pdf"}'

# 6. Borrar el item (borra también sus archivos en la BD y en S3)
curl -s -X DELETE $API/items/1 -w "%{http_code}\n"
# → 204
```

> En **PowerShell 5.1**, `curl` es un alias de `Invoke-WebRequest`. Usa `curl.exe` para los comandos con `-F`
> (subidas) y, para JSON:
> `Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/items -ContentType "application/json" -Body '{"name":"Cliente demo"}'`

### 7.3 Confirmar en AWS que todo cuadra

```bash
# Objetos en el bucket
aws s3 ls "s3://$BUCKET/uploads/"
```

```sql
-- Registros en la BD que apuntan a esos objetos
SELECT id, item_id, original_filename, s3_key, size_bytes FROM files ORDER BY id;
```

Cada `s3_key` de la tabla `files` debe existir en el bucket.

### 7.4 Tests automáticos

Los tests no usan AWS (SQLite en memoria y S3 simulado), así que no gastan nada y corren sin `.env`:

```powershell
pip install -r requirements-dev.txt
pytest
```

---

## 8. Problemas frecuentes

### `/health/db`

| Síntoma (en el log o en `detail`)                     | Causa probable y solución                                                                                     |
|-------------------------------------------------------|---------------------------------------------------------------------------------------------------------------|
| `connection timeout expired`                          | El security group no tiene tu IP actual (paso 5.2), *Public access* está en **No**, o tu red bloquea la salida al 5432 (redes corporativas o universitarias: prueba con otra red). |
| `password authentication failed`                      | `DB_USER` o `DB_PASSWORD` incorrectos. Si la contraseña tiene símbolos, ponla entre comillas simples en el `.env`. Puedes cambiar la del master en RDS → Modify. |
| `database "nttbanca" does not exist`                  | No pusiste *Initial database name*. Conéctate a la base `postgres` y ejecuta `CREATE DATABASE nttbanca;`.     |
| `no pg_hba.conf entry ... no encryption`              | `DB_SSLMODE=disable`. Usa `require`.                                                                           |
| `could not translate host name`                       | `DB_HOST` mal copiado (debe ser solo el endpoint, sin `https://` ni puerto).                                  |
| `permission denied for schema public`                 | El usuario de la API no tiene `CREATE` en `public` (paso 5.4).                                                |
| La instancia no aparece con *Public access*           | Se creó con Easy create. RDS → Modify → Connectivity → *Publicly accessible* → Apply immediately.              |
| La cuenta no tiene *Default VPC*                      | Créala en **VPC → Actions → Create default VPC**, o arma una VPC con subnets públicas y un DB subnet group.     |

### `/health/s3`

| Síntoma                                        | Causa probable y solución                                                                                  |
|------------------------------------------------|------------------------------------------------------------------------------------------------------------|
| `InvalidAccessKeyId` / `SignatureDoesNotMatch` | Keys mal copiadas o desactivadas. Revisa que no queden espacios al final en el `.env`.                      |
| `403 Forbidden` / `AccessDenied`               | La política IAM no tiene el nombre correcto del bucket, o le falta `s3:ListBucket` (paso 4).                |
| `404 Not Found` / `NoSuchBucket`               | `S3_BUCKET_NAME` mal escrito.                                                                              |
| `301` / `PermanentRedirect` / `400`            | `AWS_REGION` no coincide con la región del bucket.                                                          |
| `Unable to locate credentials`                 | Keys vacías en el `.env` y sin perfil configurado (`aws configure` o `AWS_PROFILE`).                       |
| La URL firmada da `AccessDenied` en el navegador | Expiró (`expires_in`), o la región o las keys cambiaron después de generarla.                            |

---

## 9. Costos, apagar y borrar

Estimado para la configuración de esta guía en `us-east-1`, con precios on-demand y la base encendida las 24 horas
(precios de octubre de 2026; confírmalos en la [calculadora de AWS](https://calculator.aws/#/addService/RDSPostgreSQL)):

| Concepto                            | Precio                    | Al mes (730 h) |
|-------------------------------------|---------------------------|----------------|
| Instancia `db.t4g.micro` Single-AZ  | 0.016 USD/h               | ~11.70 USD     |
| Almacenamiento gp2, 20 GB           | ~0.115 USD/GB-mes         | ~2.30 USD      |
| IPv4 pública (*Public access*)      | 0.005 USD/h               | ~3.65 USD      |
| Backups automáticos                 | gratis hasta 20 GB (el tamaño de la base) | 0 USD |
| **Total**                           |                           | **~17.60 USD** (~0.60 USD por día) |

- **Lo que te descuenta la capa gratuita depende de cuándo creaste la cuenta** (lo ves en **Billing → Free tier**):
  - **Antes del 15 de julio de 2025, y dentro de sus primeros 12 meses**: cubre 750 h al mes de `db.t4g.micro`,
    20 GB de gp2 y 20 GB de backups. Solo pagas la IPv4 pública, unos **3.65 USD al mes**. Por eso la guía usa
    gp2: gp3 no entra en la capa gratuita.
  - **Desde el 15 de julio de 2025, con el *Free plan***: los ~17.60 USD al mes se descuentan de los créditos
    (100 USD al crear la cuenta, hasta 200 USD en total). No se cobra a la tarjeta, pero la cuenta se cierra a los
    6 meses o cuando se acaban los créditos, salvo que pases al *Paid plan*.
  - **Cuenta con más de 12 meses o en *Paid plan***: pagas el total.
- **RDS se cobra por segundo** (mínimo 10 minutos). Crear la base para probar y borrarla el mismo día cuesta centavos.
- **Detenida**, la instancia deja de cobrar por hora, pero el almacenamiento se sigue cobrando.
- **Otras regiones cuestan más**: en São Paulo (`sa-east-1`) la instancia sale a 0.034 USD/h, más del doble.
- **CPU sostenida alta**: las `t4g` corren en modo *Unlimited*; si la CPU pasa su línea base de forma sostenida,
  se cobran créditos extra (0.075 USD por vCPU-hora). Con uso de desarrollo no debería pasar.
- **S3** cobra por GB almacenado y por peticiones; con archivos de prueba son centavos.
- Crea una alerta en **Billing → Budgets** (por ejemplo, 5 USD al mes) para que no haya sorpresas.

**Apagar la base cuando no la uses** (se conservan los datos; RDS la vuelve a encender sola a los 7 días):

```bash
aws rds stop-db-instance  --db-instance-identifier nttbanca-dev
aws rds start-db-instance --db-instance-identifier nttbanca-dev
```

**Borrar todo** cuando ya no lo necesites. **Esto elimina los datos de forma irreversible:**

```bash
# Bucket y todos sus archivos
aws s3 rb "s3://$BUCKET" --force

# Base de datos, sin snapshot final
aws rds delete-db-instance --db-instance-identifier nttbanca-dev \
  --skip-final-snapshot --delete-automated-backups
aws rds wait db-instance-deleted --db-instance-identifier nttbanca-dev
aws ec2 delete-security-group --group-name nttbanca-rds-dev

# Usuario IAM: primero sus access keys y su política
aws iam list-access-keys --user-name nttbanca-dev     # copia el AccessKeyId
aws iam delete-access-key --user-name nttbanca-dev --access-key-id <AccessKeyId>
aws iam delete-user-policy --user-name nttbanca-dev --policy-name nttbanca-s3-dev
aws iam delete-user --user-name nttbanca-dev
```

---

## Cuando lo despliegues

Para publicar la API en una EC2 de desarrollo junto a la RDS, sigue [DEPLOY_EC2.md](DEPLOY_EC2.md)
(`bash scripts/aws_deploy_ec2.sh`).

Lo de esta guía es para desarrollo. Para un entorno real:

- **RDS privado** (*Public access* en **No**), con la API en la misma VPC (EC2, ECS o App Runner con conector
  VPC). El security group de RDS debe aceptar el 5432 solo desde el security group de la API.
- **Sin access keys**: asigna a la API un **rol IAM** con la misma política del paso 4 y deja vacíos
  `AWS_ACCESS_KEY_ID` y `AWS_SECRET_ACCESS_KEY`. boto3 toma el rol automáticamente.
- **Secretos** (contraseña de la base) en Secrets Manager o SSM Parameter Store, inyectados como variables de
  entorno. Las variables de entorno tienen prioridad sobre el `.env`.
- Buckets y bases **separados por entorno** (dev, qa, prod), *Deletion protection* activado y backups con más
  días de retención.
- **Migraciones solo en el despliegue** (`DB_AUTO_CREATE_TABLES=false` en la app) cuando haya varias instancias.
