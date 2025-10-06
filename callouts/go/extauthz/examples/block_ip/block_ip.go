// Copyright 2025 Google LLC.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package block_ip

import (
	"context"
	"log"
	"net"

	"github.com/GoogleCloudPlatform/service-extensions/callouts/go/extauthz/internal/server"
	"github.com/GoogleCloudPlatform/service-extensions/callouts/go/extauthz/pkg/utils"
	auth "github.com/envoyproxy/go-control-plane/envoy/service/auth/v3"
	typev3 "github.com/envoyproxy/go-control-plane/envoy/type/v3"
)

// CalloutServerExample implements IP-based access control.
type CalloutServerExample struct {
	server.GRPCCalloutService
	blockedIPRange *net.IPNet
}

// NewCalloutServerExample creates a new instance of CalloutServerExample.
func NewCalloutServerExample() *CalloutServerExample {
	service := &CalloutServerExample{}

	// Parse the blocked IP range
	_, ipNet, err := net.ParseCIDR("10.0.0.0/24")
	if err != nil {
		log.Fatalf("Failed to parse blocked IP range: %v", err)
	}
	service.blockedIPRange = ipNet

	service.CheckHandler = service.handleCheck
	return service
}

// handleCheck is the handler function that processes authorization check requests.
func (s *CalloutServerExample) handleCheck(ctx context.Context, req *auth.CheckRequest) (*auth.CheckResponse, error) {
	clientIP := s.extractClientIP(req)

	// Reject if no client IP could be extracted
	if clientIP == "" {
		log.Printf("Request denied: could not extract client IP")
		return utils.DenyRequest(
			typev3.StatusCode_Forbidden,
			"",
			map[string]string{"x-client-ip-allowed": "false"},
		), nil
	}

	// Reject if IP is invalid
	if !s.isValidIP(clientIP) {
		log.Printf("Request denied: invalid IP address: %s", clientIP)
		return utils.DenyRequest(
			typev3.StatusCode_Forbidden,
			"",
			map[string]string{"x-client-ip-allowed": "false"},
		), nil
	}

	// Reject if IP is in blocked rnage
	if s.isIPBlocked(clientIP) {
		log.Printf("Request denied for blocked IP: %s", clientIP)
		return utils.DenyRequest(
			typev3.StatusCode_Forbidden,
			"",
			map[string]string{"x-client-ip-allowed": "false"},
		), nil
	}

	log.Printf("Request allowed for IP: %s", clientIP)
	return utils.AllowRequest(
		map[string]string{"x-client-ip-allowed": "true"},
	), nil
}

// extractClientIP extracts the client IP address from the request.
func (s *CalloutServerExample) extractClientIP(req *auth.CheckRequest) string {
	return utils.ExtractClientIP(req)
}

// isValidIP checks if the IP address is valid.
func (s *CalloutServerExample) isValidIP(ipStr string) bool {
	ip := net.ParseIP(ipStr)
	return ip != nil
}

// isIPBlocked checks if the IP address is in the blocked range.
func (s *CalloutServerExample) isIPBlocked(ipStr string) bool {
	ip := net.ParseIP(ipStr)
	if ip == nil {
		log.Printf("Invalid IP address in isIPBlocked: %s", ipStr)
		return true
	}

	return s.blockedIPRange.Contains(ip)
}
