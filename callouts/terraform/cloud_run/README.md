# Cloud Run Service Extensions

Deploy serverless containers with Service Extensions.

## Prerequisites

- Google Cloud Project with billing enabled
- Terraform >= 1.0
- `gcloud` CLI authenticated
- Required APIs will be enabled automatically
- [Google Cloud Terraform Best Practices](https://cloud.google.com/docs/terraform/best-practices)

## Deployment

### 1. Initialize

```bash
cd cloud_run/
terraform init
```

### 2. Configure Variables

Create `terraform.tfvars`:

```hcl
project_id = "your-project-id"
region     = "us-central1"  # Optional: change region
```

### 3. Plan and Apply

```bash
# Review changes
terraform plan -var-file="terraform.tfvars"

# Deploy infrastructure
terraform apply -var-file="terraform.tfvars"
```

## What Gets Created

### Serverless Infrastructure
- **Cloud Run Service**: Fully managed serverless platform
- **Container Image**: Sample web application
- **Auto-scaling**: 0 to 10 instances based on traffic
- **VPC Connector**: Secure connection to VPC resources

### Networking
- **VPC Network**: `service-extensions-vpc-cloudrun`
- **Subnets**: Main subnet + proxy subnet for load balancer
- **Firewall Rules**: HTTP/HTTPS access + health checks

### Load Balancing
- **Regional External Load Balancer**
- **Backend Service** with Cloud Run NEG
- **Service Extensions** for traffic processing
- **Health Checks** for service readiness

### Security & IAM
- **Service Accounts** with minimal permissions
- **IAM Bindings** for Cloud Run and service extensions
- **VPC Security** with private networking options

## Outputs

| Output | Description |
|--------|-------------|
| `load_balancer_ip` | External IP of the load balancer |

## Test Application

```bash
# Get the IP
LB_IP=$(terraform output -raw load_balancer_ip)

# Command to test the main application
curl -k -v https://$LB_IP

# Command to test the secondary application via route extension
curl -k -v https://$LB_IP -H \"x-route-to: secondary\"
```

## Cleanup

```bash
# Destroy infrastructure
terraform destroy -var-file="terraform.tfvars"
```

## Production Readiness


> This configuration is intended for **demonstration purposes only**.

Before deploying to a production environment, you must address the following:

1.  **Service Accounts**: This sample uses the default Compute Engine service account for simplicity.
    - **Risk**: Default service accounts often have the broad `Editor` role, which violates the principle of least privilege.
    - **Action**: Create dedicated Service Accounts for each service with only the minimum required permissions (e.g., `roles/run.invoker`, `roles/logging.logWriter`).

2.  **TLS Certificates**: This sample generates self-signed certificates using Terraform.
    - **Risk**: Self-signed certificates trigger browser warnings and are not secure for public traffic.
    - **Action**: Use [Google-managed SSL certificates](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/compute_managed_ssl_certificate) or provide your own valid certificates.

3.  **Deletion Protection**: `deletion_protection` is set to `false` to facilitate easy cleanup during testing.
    - **Action**: Enable deletion protection for production resources to prevent accidental data loss.