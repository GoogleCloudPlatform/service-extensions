# GCE Service Extensions

Deploy Google Compute Engine with Service Extensions.

## Prerequisites

- Google Cloud Project with billing enabled
- Terraform >= 1.0
- `gcloud` CLI authenticated
- Required APIs will be enabled automatically

## Deployment

### 1. Initialize

```bash
cd gce/
terraform init
```

### 2. Configure Variables

Create `terraform.tfvars`:

```hcl
project_id = "your-project-id"
region     = "us-central1"  # Optional: change region
```

### 3. Deploy Infrastructure

```bash
# Review changes
terraform plan -var-file="terraform.tfvars"

# Deploy infrastructure
terraform apply -var-file="terraform.tfvars"
```

## What Gets Created

### Networking
- **VPC Network**: `service-extensions-vpc`
- **Subnets**: Main subnet (10.0.1.0/24) + Proxy subnet
- **Firewall Rules**: HTTP/HTTPS access + health checks

### Compute Resources
- **VM Instances**: 2 instances with web server
- **Instance Template**: For consistent configuration
- **Instance Group**: Managed instance group for scaling

### Load Balancing
- **Regional External Load Balancer**
- **Backend Service** with health checks
- **URL Map** for traffic routing
- **Service Extensions** for traffic processing

### Security & IAM
- **Service Accounts** with minimal permissions
- **IAM Bindings** for service extensions
- **Firewall Rules** for secure access

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
curl -k -v -H 'x-route-to: secondary' https://$LB_IP
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
    - **Action**: Create dedicated Service Accounts for each service with only the minimum required permissions (e.g., `roles/logging.logWriter`, `roles/monitoring.metricWriter`).

2.  **TLS Certificates**: This sample generates self-signed certificates using Terraform.
    - **Risk**: Self-signed certificates trigger browser warnings and are not secure for public traffic.
    - **Action**: Use [Google-managed SSL certificates](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/compute_managed_ssl_certificate) or provide your own valid certificates.