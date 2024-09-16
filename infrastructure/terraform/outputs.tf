output "gke_cluster_endpoint" {
  description = "GKE cluster endpoint"
  value       = google_container_cluster.primary.endpoint
}

output "gke_cluster_name" {
  description = "GKE cluster name"
  value       = google_container_cluster.primary.name
}

output "storage_bucket_urls" {
  description = "Storage bucket URLs"
  value = {
    raw_data     = google_storage_bucket.raw_data.url
    processed_data = google_storage_bucket.processed_data.url
    model_artifacts = google_storage_bucket.model_artifacts.url
  }
}

output "firestore_database_name" {
  description = "Firestore database name"
  value       = google_firestore_database.main.name
}

output "bigquery_dataset_ids" {
  description = "BigQuery dataset IDs"
  value = {
    raw_data     = google_bigquery_dataset.raw_data.dataset_id
    processed_data = google_bigquery_dataset.processed_data.dataset_id
    analytics    = google_bigquery_dataset.analytics.dataset_id
  }
}

output "load_balancer_ip_address" {
  description = "Load Balancer IP address"
  value       = google_compute_global_address.default.address
}

output "vpc_network_name" {
  description = "VPC network name"
  value       = google_compute_network.vpc_network.name
}