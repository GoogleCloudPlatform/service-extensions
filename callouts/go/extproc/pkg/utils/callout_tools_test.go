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
	"google.golang.org/protobuf/testing/protocmp"
)

func TestHeaderImmediateResponse(t *testing.T) {
	headers := []struct{ Key, Value string }{
		{"X-Test-Header-1", "TestValue1"},
		{"X-Test-Header-2", "TestValue2"},
	}
	removeHeaders := []string{"X-Remove-Header-1", "X-Remove-Header-2"}
	appendAction := base.HeaderValueOption_APPEND_IF_EXISTS_OR_ADD
	wantResponse := &extproc.ImmediateResponse{
		Status: &httpstatus.HttpStatus{
			Code: httpstatus.StatusCode_OK,
		},
		Headers: &extproc.HeaderMutation{
			SetHeaders: []*base.HeaderValueOption{
				{
					Header: &base.HeaderValue{
						Key:      "X-Test-Header-1",
						RawValue: []byte("TestValue1"),
					},
					AppendAction: appendAction,
				},
				{
					Header: &base.HeaderValue{
						Key:      "X-Test-Header-2",
						RawValue: []byte("TestValue2"),
					},
					AppendAction: appendAction,
				},
			},
			RemoveHeaders: removeHeaders,
		},
	}

	response := HeaderImmediateResponse(httpstatus.StatusCode_OK, headers, removeHeaders, &appendAction)

	if diff := cmp.Diff(response, wantResponse, protocmp.Transform()); diff != "" {
		t.Errorf("HeaderImmediateResponse mismatch (-want +got):\n%s", diff)
	}
}

func TestAddHeaderMutation(t *testing.T) {
	addHeaders := []struct{ Key, Value string }{
		{"X-Add-Header-1", "AddValue1"},
		{"X-Add-Header-2", "AddValue2"},
	}
	removeHeaders := []string{"X-Remove-Header-1", "X-Remove-Header-2"}
	clearRouteCache := true
	appendAction := base.HeaderValueOption_APPEND_IF_EXISTS_OR_ADD
	wantResponse := &extproc.HeadersResponse{
		Response: &extproc.CommonResponse{
			HeaderMutation: &extproc.HeaderMutation{
				SetHeaders: []*base.HeaderValueOption{
					{
						Header: &base.HeaderValue{
							Key:      "X-Add-Header-1",
							RawValue: []byte("AddValue1"),
						},
						AppendAction: appendAction,
					},
					{
						Header: &base.HeaderValue{
							Key:      "X-Add-Header-2",
							RawValue: []byte("AddValue2"),
						},
						AppendAction: appendAction,
					},
				},
				RemoveHeaders: removeHeaders,
			},
			ClearRouteCache: clearRouteCache,
		},
	}

	response := AddHeaderMutation(addHeaders, removeHeaders, clearRouteCache, &appendAction)

	if diff := cmp.Diff(response, wantResponse, protocmp.Transform()); diff != "" {
		t.Errorf("AddHeaderMutation mismatch (-want +got):\n%s", diff)
	}
}

func TestAddBodyMutations(t *testing.T) {
	tests := []struct {
		name            string
		body            string
		clearBody       bool
		clearRouteCache bool
		wantResponse    *extproc.BodyResponse
	}{
		{
			name:            "AddBodyStringMutation with new body",
			body:            "new-body",
			clearRouteCache: true,
			wantResponse: &extproc.BodyResponse{
				Response: &extproc.CommonResponse{
					BodyMutation: &extproc.BodyMutation{
						Mutation: &extproc.BodyMutation_Body{
							Body: []byte("new-body"),
						},
					},
					ClearRouteCache: true,
				},
			},
		},
		{
			name:            "AddBodyClearMutation to clear body",
			clearBody:       true,
			clearRouteCache: true,
			wantResponse: &extproc.BodyResponse{
				Response: &extproc.CommonResponse{
					BodyMutation: &extproc.BodyMutation{
						Mutation: &extproc.BodyMutation_ClearBody{
							ClearBody: true,
						},
					},
					ClearRouteCache: true,
				},
			},
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

			if diff := cmp.Diff(response, tt.wantResponse, protocmp.Transform()); diff != "" {
				t.Errorf("AddBodyMutation mismatch (-want +got):\n%s", diff)
			}
		})
	}
}
