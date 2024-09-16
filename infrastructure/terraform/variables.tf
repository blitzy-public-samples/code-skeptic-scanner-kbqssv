# Project ID variable
variable "project_id" {
  description = "The ID of the Google Cloud project"
  type        = string
}

# Region and zone variables
variable "region" {
  description = "The region to deploy resources"
  type        = string
  default     = "us-central1"
}

variable "zone" {
  description = "The zone to deploy resources"
  type        = string
  default     = "us-central1-a"
}

# GKE cluster configuration variables
variable "gke_cluster_name" {
  description = "The name of the GKE cluster"
  type        = string
  default     = "main-cluster"
}

variable "gke_num_nodes" {
  description = "Number of nodes in the GKE cluster"
  type        = number
  default     = 3
}

variable "gke_machine_type" {
  description = "Machine type for GKE nodes"
  type        = string
  default     = "n1-standard-2"
}

# Storage bucket name variables
variable "raw_data_bucket_name" {
  description = "Name of the bucket for raw data storage"
  type        = string
}

variable "processed_data_bucket_name" {
  description = "Name of the bucket for processed data storage"
  type        = string
}

# Firestore location variable
variable "firestore_location" {
  description = "Location for Firestore database"
  type        = string
  default     = "us-central"
}

# BigQuery dataset name variables
variable "raw_data_dataset" {
  description = "Name of the BigQuery dataset for raw data"
  type        = string
  default     = "raw_data"
}

variable "processed_data_dataset" {
  description = "Name of the BigQuery dataset for processed data"
  type        = string
  default     = "processed_data"
}

# Network configuration variables
variable "network_name" {
  description = "Name of the VPC network"
  type        = string
  default     = "main-network"
}

variable "subnet_name" {
  description = "Name of the subnet"
  type        = string
  default     = "main-subnet"
}

variable "subnet_cidr" {
  description = "CIDR range for the subnet"
  type        = string
  default     = "10.0.0.0/24"
}