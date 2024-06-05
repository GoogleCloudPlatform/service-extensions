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
	"fmt"
	"github.com/dgrijalva/jwt-go"
	base "github.com/envoyproxy/go-control-plane/envoy/config/core/v3"
	extproc "github.com/envoyproxy/go-control-plane/envoy/service/ext_proc/v3"
	"github.com/stretchr/testify/assert"
	"io/ioutil"
	"regexp"
	"service-extensions-samples/extproc/examples/jwt_auth"
	"testing"
	"time"
)

func generateTestJWTToken(privateKey []byte, claims jwt.MapClaims) (string, error) {
	token := jwt.NewWithClaims(jwt.SigningMethodRS256, claims)
	privateKeyParsed, err := jwt.ParseRSAPrivateKeyFromPEM(privateKey)
	if err != nil {
		return "", err
	}
	return token.SignedString(privateKeyParsed)
}

func TestHandleRequestHeaders_ValidToken(t *testing.T) {
	// Load test keys
	privateKey, err := ioutil.ReadFile("../ssl_creds/localhost.key")
	assert.NoError(t, err, "failed to load private key")

	// Create test JWT token
	now := time.Now().Unix()
	claims := jwt.MapClaims{
		"sub":  "1234567890",
		"name": "John Doe",
		"iat":  now,
		"exp":  now + 3600,
	}
	tokenString, err := generateTestJWTToken(privateKey, claims)
	assert.NoError(t, err, "failed to generate test JWT token")

	headers := &extproc.HttpHeaders{
		Headers: &base.HeaderMap{
			Headers: []*base.HeaderValue{
				{
					Key:      "Authorization",
					RawValue: []byte("Bearer " + tokenString),
				},
			},
		},
	}

	// Create an instance of ExampleCalloutService with overridden public key path
	service := jwt_auth.NewExampleCalloutServiceWithKeyPath("../ssl_creds/publickey.pem")

	// Call the HandleRequestHeaders method
	response, err := service.HandleRequestHeaders(headers)

	// Assert that no error occurred
	assert.NoError(t, err)

	// Assert that the response is not nil
	assert.NotNil(t, response)

	// Prepare expected decoded items without iat and exp
	expectedItems := []struct{ Key, Value string }{
		{"decoded-sub", "1234567890"},
		{"decoded-name", "John Doe"},
	}

	// Validate the response headers
	requestHeaders := response.GetRequestHeaders().GetResponse()
	for _, item := range expectedItems {
		found := false
		for _, header := range requestHeaders.GetHeaderMutation().GetSetHeaders() {
			if header.GetHeader().GetKey() == item.Key && string(header.GetHeader().GetRawValue()) == item.Value {
				found = true
				break
			}
		}
		assert.True(t, found, fmt.Sprintf("header %s: %s not found in response", item.Key, item.Value))
	}

	// Validate iat and exp separately using regex patterns
	iatPattern := regexp.MustCompile(`^\d+(\.\d+)?(e[\+\-]?\d+)?$`)
	expPattern := regexp.MustCompile(`^\d+(\.\d+)?(e[\+\-]?\d+)?$`)

	iatFound := false
	expFound := false
	for _, header := range requestHeaders.GetHeaderMutation().GetSetHeaders() {
		key := header.GetHeader().GetKey()
		value := string(header.GetHeader().GetRawValue())
		if key == "decoded-iat" {
			assert.True(t, iatPattern.MatchString(value), fmt.Sprintf("decoded-iat value %s does not match expected pattern", value))
			iatFound = true
		}
		if key == "decoded-exp" {
			assert.True(t, expPattern.MatchString(value), fmt.Sprintf("decoded-exp value %s does not match expected pattern", value))
			expFound = true
		}
	}

	assert.True(t, iatFound, "header decoded-iat not found or mismatched in response")
	assert.True(t, expFound, "header decoded-exp not found or mismatched in response")
}

func TestHandleRequestHeaders_InvalidToken(t *testing.T) {

	headers := &extproc.HttpHeaders{
		Headers: &base.HeaderMap{
			Headers: []*base.HeaderValue{
				{
					Key:      "Authorization",
					RawValue: []byte("Bearer invalidtoken"),
				},
			},
		},
	}

	// Create an instance of ExampleCalloutService with test public key path
	service := jwt_auth.NewExampleCalloutServiceWithKeyPath("../ssl_creds/publickey.pem")

	service.PublicKey = []byte("invalidpublickey")

	// Call the HandleRequestHeaders method
	_, err := service.HandleRequestHeaders(headers)

	// Assert that an error occurred
	assert.Error(t, err)

	// Assert that the error is a permission denied error
	assert.Contains(t, err.Error(), "PermissionDenied")

	// Assert that the error message contains "Authorization token is invalid"
	assert.Contains(t, err.Error(), "Authorization token is invalid")
}
