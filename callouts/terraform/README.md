# Google Cloud Service Extensions - Terraform Configurations

This repository contains Terraform configurations for deploying Google Cloud Service Extensions across three different compute platforms: **Google Compute Engine (GCE)**, **Google Kubernetes Engine (GKE)**, and **Cloud Run**.

## Quick Start

Choose your preferred compute platform and follow the corresponding setup guide:

| Platform | Description | Documentation |
|----------|-------------|---------------|
| **[GCE](./gce/)** | Virtual machines with load balancer and service extensions | [ GCE Setup Guide](./gce/README.md) |
| **[GKE](./gke/)** | Kubernetes cluster with containerized applications | [ GKE Setup Guide](./gke/README.md) |
| **[Cloud Run](./cloud_run/)** | Serverless containers with automatic scaling | [ Cloud Run Setup Guide](./cloud_run/README.md) |

## Prerequisites

Before deploying any configuration, ensure you have:

- **Google Cloud Project** with billing enabled
- **Terraform** >= 1.0 installed
- **Google Cloud SDK** installed and authenticated
- Required **IAM permissions** for the services you plan to deploy

## Architecture Overview

All three setups implement similar patterns with platform-specific optimizations:

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Internet      │    │  Load Balancer   │    │  Compute        │
│   Traffic       │───▶│  + Service       │───▶│  Platform       │
│                 │    │  Extensions      │    │  (GCE/GKE/CR)   │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

- **Regional External Load Balancer** for traffic distribution
- **Service Extensions** for traffic processing and security
- **VPC Network** with proper subnet configuration
- **IAM roles** and service accounts for secure access

## Additional Resources

- [Google Cloud Service Extensions Documentation](https://cloud.google.com/service-extensions)
- [Terraform Google Provider Documentation](https://registry.terraform.io/providers/hashicorp/google/latest/docs)
- [Google Cloud Terraform Best Practices](https://cloud.google.com/docs/terraform/best-practices)