// Copyright 2024 Google LLC.
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

package utils

import (
	"testing"

	base "github.com/envoyproxy/go-control-plane/envoy/config/core/v3"
	extproc "github.com/envoyproxy/go-control-plane/envoy/service/ext_proc/v3"
	httpstatus "github.com/envoyproxy/go-control-plane/envoy/type/v3"
	"github.com/google/go-cmp/cmp"
)

func TestHeaderImmediateResponse(t *testing.T) {
	headers := []struct{ Key, Value string }{
		{"X-Test-Header-1", "TestValue1"},
		{"X-Test-Header-2", "TestValue2"},
	}
	removeHeaders := []string{"X-Remove-Header-1", "X-Remove-Header-2"}
	appendAction := base.HeaderValueOption_APPEND_IF_EXISTS_OR_ADD
	response := HeaderImmediateResponse(httpstatus.StatusCode_OK, headers, removeHeaders, &appendAction)

	// Check if the status code is set correctly
	if diff := cmp.Diff(response.Status.Code, httpstatus.StatusCode_OK); diff != "" {
		t.Errorf("HeaderImmediateResponse status code mismatch (-want +got):\n%s", diff)
	}

	// Check if the correct number of headers are set
	if len(response.Headers.SetHeaders) != len(headers) {
		t.Fatalf("HeaderImmediateResponse got %d headers, want %d", len(response.Headers.SetHeaders), len(headers))
	}

	// Check if each header is set correctly
	for i, h := range headers {
		header := response.Headers.SetHeaders[i]
		if diff := cmp.Diff(header.Header.Key, h.Key); diff != "" {
			t.Errorf("HeaderImmediateResponse header key mismatch (-want +got):\n%s", diff)
		}
		if diff := cmp.Diff(string(header.Header.RawValue), h.Value); diff != "" {
			t.Errorf("HeaderImmediateResponse header value mismatch (-want +got):\n%s", diff)
		}
		if diff := cmp.Diff(header.AppendAction, appendAction); diff != "" {
			t.Errorf("HeaderImmediateResponse append action mismatch (-want +got):\n%s", diff)
		}
	}

	// Check if the correct number of headers are removed
	if len(response.Headers.RemoveHeaders) != len(removeHeaders) {
		t.Fatalf("HeaderImmediateResponse got %d removed headers, want %d", len(response.Headers.RemoveHeaders), len(removeHeaders))
	}

	// Check if each header is removed correctly
	for i, h := range removeHeaders {
		if diff := cmp.Diff(response.Headers.RemoveHeaders[i], h); diff != "" {
			t.Errorf("HeaderImmediateResponse remove header mismatch (-want +got):\n%s", diff)
		}
	}
}

// TestAddHeaderMutation tests the AddHeaderMutation function to ensure it correctly sets, removes headers, and clears route cache.
func TestAddHeaderMutation(t *testing.T) {
	addHeaders := []struct{ Key, Value string }{
		{"X-Add-Header-1", "AddValue1"},
		{"X-Add-Header-2", "AddValue2"},
	}
	removeHeaders := []string{"X-Remove-Header-1", "X-Remove-Header-2"}
	clearRouteCache := true
	appendAction := base.HeaderValueOption_APPEND_IF_EXISTS_OR_ADD
	response := AddHeaderMutation(addHeaders, removeHeaders, clearRouteCache, &appendAction)

	// Check if HeaderMutation is not nil
	if response.Response.HeaderMutation == nil {
		t.Fatal("AddHeaderMutation got nil HeaderMutation, want non-nil")
	}

	// Check if the correct number of headers are set
	if len(response.Response.HeaderMutation.SetHeaders) != len(addHeaders) {
		t.Fatalf("AddHeaderMutation got %d set headers, want %d", len(response.Response.HeaderMutation.SetHeaders), len(addHeaders))
	}

	// Check if each added header is set correctly using cmp.Diff
	for i, h := range addHeaders {
		header := response.Response.HeaderMutation.SetHeaders[i]
		if diff := cmp.Diff(header.Header.Key, h.Key); diff != "" {
			t.Errorf("AddHeaderMutation header key mismatch (-want +got):\n%s", diff)
		}
		if diff := cmp.Diff(string(header.Header.RawValue), h.Value); diff != "" {
			t.Errorf("AddHeaderMutation header value mismatch (-want +got):\n%s", diff)
		}
		if diff := cmp.Diff(header.AppendAction, appendAction); diff != "" {
			t.Errorf("AddHeaderMutation append action mismatch (-want +got):\n%s", diff)
		}
	}

	// Check if the correct number of headers are removed
	if len(response.Response.HeaderMutation.RemoveHeaders) != len(removeHeaders) {
		t.Fatalf("AddHeaderMutation got %d remove headers, want %d", len(response.Response.HeaderMutation.RemoveHeaders), len(removeHeaders))
	}

	// Check if each removed header is set correctly using cmp.Diff
	for i, h := range removeHeaders {
		if diff := cmp.Diff(response.Response.HeaderMutation.RemoveHeaders[i], h); diff != "" {
			t.Errorf("AddHeaderMutation remove header mismatch (-want +got):\n%s", diff)
		}
	}

	// Check if ClearRouteCache is set correctly using cmp.Diff
	if diff := cmp.Diff(response.Response.ClearRouteCache, clearRouteCache); diff != "" {
		t.Errorf("AddHeaderMutation ClearRouteCache mismatch (-want +got):\n%s", diff)
	}
}

// TestAddBodyMutations tests the AddBodyStringMutation and AddBodyClearMutation functions
func TestAddBodyMutations(t *testing.T) {
	tests := []struct {
		name            string
		body            string
		clearBody       bool
		clearRouteCache bool
		wantBody        string
		wantClearBody   bool
	}{
		{
			name:            "AddBodyStringMutation with new body",
			body:            "new-body",
			clearBody:       false,
			clearRouteCache: true,
			wantBody:        "new-body",
			wantClearBody:   false,
		},
		{
			name:            "AddBodyClearMutation to clear body",
			body:            "",
			clearBody:       true,
			clearRouteCache: true,
			wantBody:        "",
			wantClearBody:   true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			var response *extproc.BodyResponse
			if tt.clearBody {
				response = AddBodyClearMutation(tt.clearRouteCache)
			} else {
				response = AddBodyStringMutation(tt.body, tt.clearRouteCache)
			}

			// Check if BodyMutation is not nil
			if response.Response.BodyMutation == nil {
				t.Fatal("AddBodyMutation got nil BodyMutation, want non-nil")
			}

			// Check if the body is set correctly
			if diff := cmp.Diff(string(response.Response.BodyMutation.GetBody()), tt.wantBody); diff != "" {
				t.Errorf("AddBodyMutation body mismatch (-want +got):\n%s", diff)
			}

			// Check if ClearBody is set correctly
			if diff := cmp.Diff(response.Response.BodyMutation.GetClearBody(), tt.wantClearBody); diff != "" {
				t.Errorf("AddBodyMutation clear body mismatch (-want +got):\n%s", diff)
			}

			// Check if ClearRouteCache is set correctly
			if diff := cmp.Diff(response.Response.ClearRouteCache, tt.clearRouteCache); diff != "" {
				t.Errorf("AddBodyMutation clear route cache mismatch (-want +got):\n%s", diff)
			}
		})
	}
}
