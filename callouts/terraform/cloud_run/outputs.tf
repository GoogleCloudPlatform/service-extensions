# Copyright 2025 Google LLC.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

output "main_application_load_balancer_ip" {
  description = "The IP address of the main application load balancer"
  value       = google_compute_address.main_lb_ip.address
}

output "test_command_main" {
  description = "Command to test the main application"
  value       = "curl -k -v https://${google_compute_address.main_lb_ip.address}/"
}

output "test_command_secondary" {
  description = "Command to test the secondary application via route extension"
  value       = "curl -k -v https://${google_compute_address.main_lb_ip.address}/ -H \"x-route-to: secondary\""
}