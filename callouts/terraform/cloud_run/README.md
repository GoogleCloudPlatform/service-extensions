# Cloud Run Service Extensions

Deploy serverless containers with Service Extensions.

## Prerequisites

- Google Cloud Project with billing enabled
- Terraform >= 1.0
- `gcloud` CLI authenticated
- Required APIs will be enabled automatically

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
- **Cloud Run Services**: Main app, secondary app, and callout services
- **Container Images**: Sample web applications
- **Auto-scaling**: 0 to 10 instances based on traffic

### Networking
- **VPC Network**: `service-extensions-vpc-cloudrun`
- **Subnets**: Main subnet + proxy subnet for load balancer
- **Serverless NEGs**: Network Endpoint Groups for Cloud Run services

### Load Balancing
- **Regional External Load Balancer**
- **Backend Services** with Cloud Run NEGs
- **Service Extensions** for traffic and route processing
- **SSL Certificate** for HTTPS traffic

### Security & IAM
- **IAM Bindings** for Cloud Run invoker permissions
- **Service Extensions** integration for traffic processing

## Outputs

| Output | Description |
|--------|-------------|
| `main_application_load_balancer_ip` | External IP of the load balancer |
| `test_command_main` | Command to test the main application |
| `test_command_secondary` | Command to test the secondary application via route extension |

## Test Application

```bash
# Get the IP
LB_IP=$(terraform output -raw main_application_load_balancer_ip)

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
    - **Action**: Create dedicated Service Accounts for each service with only the minimum required permissions (e.g., `roles/run.invoker`, `roles/logging.logWriter`).

2.  **TLS Certificates**: This sample generates self-signed certificates using Terraform.
    - **Risk**: Self-signed certificates trigger browser warnings and are not secure for public traffic.
    - **Action**: Use [Google-managed SSL certificates](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/compute_managed_ssl_certificate) or provide your own valid certificates.

3.  **Deletion Protection**: `deletion_protection` is set to `false` to facilitate easy cleanup during testing.
    - **Action**: Enable deletion protection for production resources to prevent accidental data loss.