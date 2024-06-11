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
	httpstatus "github.com/envoyproxy/go-control-plane/envoy/type/v3"
)

// TestHeaderImmediateResponse tests the HeaderImmediateResponse function to ensure it correctly sets headers and status code.
func TestHeaderImmediateResponse(t *testing.T) {
	headers := []struct{ Key, Value string }{
		{"X-Test-Header-1", "TestValue1"},
		{"X-Test-Header-2", "TestValue2"},
	}
	appendAction := base.HeaderValueOption_APPEND_IF_EXISTS_OR_ADD
	response := HeaderImmediateResponse(httpstatus.StatusCode_OK, headers, &appendAction)

	// Check if the status code is set correctly
	if got, want := response.Status.Code, httpstatus.StatusCode_OK; got != want {
		t.Errorf("HeaderImmediateResponse got status code %v, want %v", got, want)
	}

	// Check if the correct number of headers are set
	if len(response.Headers.SetHeaders) != len(headers) {
		t.Fatalf("HeaderImmediateResponse got %d headers, want %d", len(response.Headers.SetHeaders), len(headers))
	}

	// Check if each header is set correctly
	for i, h := range headers {
		header := response.Headers.SetHeaders[i]
		if got, want := header.Header.Key, h.Key; got != want {
			t.Errorf("HeaderImmediateResponse got header key %v, want %v", got, want)
		}
		if got, want := header.Header.Value, h.Value; got != want {
			t.Errorf("HeaderImmediateResponse got header value %v, want %v", got, want)
		}
		if got, want := header.AppendAction, appendAction; got != want {
			t.Errorf("HeaderImmediateResponse got append action %v, want %v", got, want)
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

	// Check if each added header is set correctly
	for i, h := range addHeaders {
		header := response.Response.HeaderMutation.SetHeaders[i]
		if got, want := header.Header.Key, h.Key; got != want {
			t.Errorf("AddHeaderMutation got header key %v, want %v", got, want)
		}
		if got, want := string(header.Header.RawValue), h.Value; got != want {
			t.Errorf("AddHeaderMutation got header value %v, want %v", got, want)
		}
		if got, want := header.AppendAction, appendAction; got != want {
			t.Errorf("AddHeaderMutation got append action %v, want %v", got, want)
		}
	}

	// Check if the correct number of headers are removed
	if len(response.Response.HeaderMutation.RemoveHeaders) != len(removeHeaders) {
		t.Fatalf("AddHeaderMutation got %d remove headers, want %d", len(response.Response.HeaderMutation.RemoveHeaders), len(removeHeaders))
	}

	// Check if each removed header is set correctly
	for i, h := range removeHeaders {
		if got, want := response.Response.HeaderMutation.RemoveHeaders[i], h; got != want {
			t.Errorf("AddHeaderMutation got remove header %v, want %v", got, want)
		}
	}

	// Check if ClearRouteCache is set correctly
	if got, want := response.Response.ClearRouteCache, clearRouteCache; got != want {
		t.Errorf("AddHeaderMutation got ClearRouteCache %v, want %v", got, want)
	}
}

// TestAddBodyMutation tests the AddBodyMutation function to ensure it correctly sets the body mutation and clears route cache.
func TestAddBodyMutation(t *testing.T) {
	body := "new-body"
	clearBody := false
	clearRouteCache := true
	response := AddBodyMutation(body, clearBody, clearRouteCache)

	// Check if BodyMutation is not nil
	if response.Response.BodyMutation == nil {
		t.Fatal("AddBodyMutation got nil BodyMutation, want non-nil")
	}

	// Check if the body is set correctly
	if got, want := string(response.Response.BodyMutation.GetBody()), body; got != want {
		t.Errorf("AddBodyMutation got body %v, want %v", got, want)
	}

	// Check if ClearBody is set correctly
	if got, want := response.Response.BodyMutation.GetClearBody(), clearBody; got != want {
		t.Errorf("AddBodyMutation got ClearBody %v, want %v", got, want)
	}

	// Check if ClearRouteCache is set correctly
	if got, want := response.Response.ClearRouteCache, clearRouteCache; got != want {
		t.Errorf("AddBodyMutation got ClearRouteCache %v, want %v", got, want)
	}
}
