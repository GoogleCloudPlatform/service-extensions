// Copyright 2024 Google LLC.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//	http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package tests

import (
	"service-extensions-samples/extproc/internal/server"
)

// DefaultConfig returns a default server configuration.
func DefaultConfig() server.ServerConfig {
	return server.ServerConfig{
		Address:            "0.0.0.0:8443",
		InsecureAddress:    "0.0.0.0:8181",
		HealthCheckAddress: "0.0.0.0:8000",
		CertFile:           "../ssl_creds/localhost.crt",
		KeyFile:            "../ssl_creds/localhost.key",
	}
}

// InsecureConfig returns a configuration with only the insecure address set.
func InsecureConfig() server.ServerConfig {
	config := DefaultConfig()
	config.Address = ""
	return config
}
