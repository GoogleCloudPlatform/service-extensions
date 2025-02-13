use crate::envoy::{
    config::core::v3::{HeaderValue, HeaderValueOption},
    service::ext_proc::v3::{
        ProcessingResponse,
        HeadersResponse,
        CommonResponse,
        HeaderMutation,
        processing_response::Response as ProcessingResponseType,
    },
};

pub fn add_header_mutation(
    headers_to_add: Vec<(&str, &str)>,
    headers_to_remove: Vec<&str>,
    clear_route_cache: bool,
) -> ProcessingResponse {
    let mut header_mutation = HeaderMutation::default();

    // Add headers
    header_mutation.set_headers = headers_to_add
        .into_iter()
        .map(|(key, value)| HeaderValueOption {
            header: Some(HeaderValue {
                key: key.to_string(),
                raw_value: value.as_bytes().to_vec(),
                ..Default::default()
            }),
            append: None,  // Keep for backwards compatibility
            append_action: 0,  // APPEND_NONE
            keep_empty_value: false,
        })
        .collect();

    // Remove headers
    header_mutation.remove_headers = headers_to_remove
        .into_iter()
        .map(String::from)
        .collect();

    let headers_response = HeadersResponse {
        response: Some(CommonResponse {
            header_mutation: Some(header_mutation),
            clear_route_cache,
            ..Default::default()
        }),
    };

    ProcessingResponse {
        response: Some(ProcessingResponseType::ResponseHeaders(headers_response)),
        mode_override: None,
        dynamic_metadata: None,
        override_message_timeout: None,
    }
}