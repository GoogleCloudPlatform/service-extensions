// Copyright 2025 Google LLC
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
#![allow(clippy::all)]

pub mod envoy {
    pub mod config {
        pub mod core {
            pub mod v3 {
                include!("envoy.config.core.v3.rs");
            }
        }
    }

    pub mod service {
        pub mod ext_proc {
            pub mod v3 {
                include!("envoy.service.ext_proc.v3.rs");
            }
        }
    }

    pub mod extensions {
        pub mod filters {
            pub mod http {
                pub mod ext_proc {
                    pub mod v3 {
                        include!("envoy.extensions.filters.http.ext_proc.v3.rs");
                    }
                }
            }
        }
    }

    pub mod r#type {
        pub mod v3 {
            include!("envoy.r#type.v3.rs");
        }
    }
}

pub mod xds {
    pub mod core {
        pub mod v3 {
            include!("xds.core.v3.rs");
        }
    }
    pub mod annotations {
        pub mod v3 {
            include!("xds.annotations.v3.rs");
        }
    }
}

pub mod udpa {
    pub mod annotations {
        include!("udpa.annotations.rs");
    }
}

pub mod validate {
    include!("validate.rs");
}
