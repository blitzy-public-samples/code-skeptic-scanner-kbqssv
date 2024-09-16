# HUMAN ASSISTANCE NEEDED
# Please review and adjust the following configuration as needed:
# - Ensure the project ID, region, and zone are correct
# - Verify the GKE cluster configuration meets your requirements
# - Confirm the Cloud Storage bucket names are globally unique
# - Check if the Firestore database location is appropriate
# - Validate the BigQuery dataset and table configurations
# - Review the Cloud CDN, Load Balancer, and Cloud Armor settings
# - Confirm the VPC and subnet configurations are correct

terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 4.0"
    }
  }
}

provider "google" {
  project = "your-project-id"
  region  = "us-central1"
  zone    = "us-central1-a"
}

# GKE Cluster
resource "google_container_cluster" "primary" {
  name     = "primary-cluster"
  location = "us-central1"

  remove_default_node_pool = true
  initial_node_count       = 1

  network    = google_compute_network.vpc.name
  subnetwork = google_compute_subnetwork.subnet.name
}

resource "google_container_node_pool" "primary_nodes" {
  name       = "primary-node-pool"
  location   = "us-central1"
  cluster    = google_container_cluster.primary.name
  node_count = 3

  node_config {
    machine_type = "e2-medium"
  }
}

# Cloud Storage Buckets
resource "google_storage_bucket" "static_assets" {
  name          = "your-project-static-assets"
  location      = "US"
  force_destroy = true
}

resource "google_storage_bucket" "user_uploads" {
  name          = "your-project-user-uploads"
  location      = "US"
  force_destroy = true
}

# Firestore Database
resource "google_firestore_database" "database" {
  project     = "your-project-id"
  name        = "(default)"
  location_id = "nam5"
  type        = "FIRESTORE_NATIVE"
}

# BigQuery Datasets and Tables
resource "google_bigquery_dataset" "analytics" {
  dataset_id = "analytics"
  location   = "US"
}

resource "google_bigquery_table" "user_events" {
  dataset_id = google_bigquery_dataset.analytics.dataset_id
  table_id   = "user_events"

  schema = <<EOF
[
  {
    "name": "user_id",
    "type": "STRING",
    "mode": "REQUIRED"
  },
  {
    "name": "event_type",
    "type": "STRING",
    "mode": "REQUIRED"
  },
  {
    "name": "timestamp",
    "type": "TIMESTAMP",
    "mode": "REQUIRED"
  }
]
EOF
}

# Cloud CDN and Load Balancer
resource "google_compute_global_address" "default" {
  name = "global-appserver-ip"
}

resource "google_compute_backend_service" "default" {
  name        = "backend-service"
  port_name   = "http"
  protocol    = "HTTP"
  timeout_sec = 10

  health_checks = [google_compute_health_check.default.id]
}

resource "google_compute_url_map" "default" {
  name            = "url-map"
  default_service = google_compute_backend_service.default.id
}

resource "google_compute_target_http_proxy" "default" {
  name    = "http-proxy"
  url_map = google_compute_url_map.default.id
}

resource "google_compute_global_forwarding_rule" "default" {
  name       = "global-rule"
  target     = google_compute_target_http_proxy.default.id
  port_range = "80"
  ip_address = google_compute_global_address.default.address
}

# Cloud Armor WAF
resource "google_compute_security_policy" "policy" {
  name = "my-policy"

  rule {
    action   = "deny(403)"
    priority = "1000"
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["9.9.9.0/24"]
      }
    }
    description = "Deny access to IPs in 9.9.9.0/24"
  }

  rule {
    action   = "allow"
    priority = "2147483647"
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    description = "Default rule, allow all traffic"
  }
}

# VPC and Subnets
resource "google_compute_network" "vpc" {
  name                    = "my-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "subnet" {
  name          = "my-subnet"
  ip_cidr_range = "10.0.0.0/24"
  region        = "us-central1"
  network       = google_compute_network.vpc.id
}