"""
@generated
cargo-raze generated Bazel file.

DO NOT EDIT! Replaced on runs of cargo-raze
"""

load("@bazel_tools//tools/build_defs/repo:git.bzl", "new_git_repository")  # buildifier: disable=load
load("@bazel_tools//tools/build_defs/repo:http.bzl", "http_archive")  # buildifier: disable=load
load("@bazel_tools//tools/build_defs/repo:utils.bzl", "maybe")  # buildifier: disable=load

def raze_fetch_remote_crates():
    """This function defines a collection of repos and should be called in a WORKSPACE file"""
    maybe(
        http_archive,
        name = "raze__aho_corasick__1_0_2",
        url = "https://crates.io/api/v1/crates/aho-corasick/1.0.2/download",
        type = "tar.gz",
        sha256 = "43f6cb1bf222025340178f382c426f13757b2960e89779dfcb319c32542a5a41",
        strip_prefix = "aho-corasick-1.0.2",
        build_file = Label("//cargo/remote:BUILD.aho-corasick-1.0.2.bazel"),
    )

    maybe(
        http_archive,
        name = "raze__form_urlencoded__1_2_0",
        url = "https://crates.io/api/v1/crates/form_urlencoded/1.2.0/download",
        type = "tar.gz",
        sha256 = "a62bc1cf6f830c2ec14a513a9fb124d0a213a629668a4186f329db21fe045652",
        strip_prefix = "form_urlencoded-1.2.0",
        build_file = Label("//cargo/remote:BUILD.form_urlencoded-1.2.0.bazel"),
    )

    maybe(
        http_archive,
        name = "raze__idna__0_4_0",
        url = "https://crates.io/api/v1/crates/idna/0.4.0/download",
        type = "tar.gz",
        sha256 = "7d20d6b07bfbc108882d88ed8e37d39636dcc260e15e30c45e6ba089610b917c",
        strip_prefix = "idna-0.4.0",
        build_file = Label("//cargo/remote:BUILD.idna-0.4.0.bazel"),
    )

    maybe(
        http_archive,
        name = "raze__log__0_4_19",
        url = "https://crates.io/api/v1/crates/log/0.4.19/download",
        type = "tar.gz",
        sha256 = "b06a4cde4c0f271a446782e3eff8de789548ce57dbc8eca9292c27f4a42004b4",
        strip_prefix = "log-0.4.19",
        build_file = Label("//cargo/remote:BUILD.log-0.4.19.bazel"),
    )

    maybe(
        http_archive,
        name = "raze__memchr__2_5_0",
        url = "https://crates.io/api/v1/crates/memchr/2.5.0/download",
        type = "tar.gz",
        sha256 = "2dffe52ecf27772e601905b7522cb4ef790d2cc203488bbd0e2fe85fcb74566d",
        strip_prefix = "memchr-2.5.0",
        build_file = Label("//cargo/remote:BUILD.memchr-2.5.0.bazel"),
    )

    maybe(
        http_archive,
        name = "raze__percent_encoding__2_3_0",
        url = "https://crates.io/api/v1/crates/percent-encoding/2.3.0/download",
        type = "tar.gz",
        sha256 = "9b2a4787296e9989611394c33f193f676704af1686e70b8f8033ab5ba9a35a94",
        strip_prefix = "percent-encoding-2.3.0",
        build_file = Label("//cargo/remote:BUILD.percent-encoding-2.3.0.bazel"),
    )

    maybe(
        http_archive,
        name = "raze__regex__1_9_1",
        url = "https://crates.io/api/v1/crates/regex/1.9.1/download",
        type = "tar.gz",
        sha256 = "b2eae68fc220f7cf2532e4494aded17545fce192d59cd996e0fe7887f4ceb575",
        strip_prefix = "regex-1.9.1",
        build_file = Label("//cargo/remote:BUILD.regex-1.9.1.bazel"),
    )

    maybe(
        http_archive,
        name = "raze__regex_automata__0_3_3",
        url = "https://crates.io/api/v1/crates/regex-automata/0.3.3/download",
        type = "tar.gz",
        sha256 = "39354c10dd07468c2e73926b23bb9c2caca74c5501e38a35da70406f1d923310",
        strip_prefix = "regex-automata-0.3.3",
        build_file = Label("//cargo/remote:BUILD.regex-automata-0.3.3.bazel"),
    )

    maybe(
        http_archive,
        name = "raze__regex_syntax__0_7_4",
        url = "https://crates.io/api/v1/crates/regex-syntax/0.7.4/download",
        type = "tar.gz",
        sha256 = "e5ea92a5b6195c6ef2a0295ea818b312502c6fc94dde986c5553242e18fd4ce2",
        strip_prefix = "regex-syntax-0.7.4",
        build_file = Label("//cargo/remote:BUILD.regex-syntax-0.7.4.bazel"),
    )

    maybe(
        http_archive,
        name = "raze__tinyvec__1_6_0",
        url = "https://crates.io/api/v1/crates/tinyvec/1.6.0/download",
        type = "tar.gz",
        sha256 = "87cc5ceb3875bb20c2890005a4e226a4651264a5c75edb2421b52861a0a0cb50",
        strip_prefix = "tinyvec-1.6.0",
        build_file = Label("//cargo/remote:BUILD.tinyvec-1.6.0.bazel"),
    )

    maybe(
        http_archive,
        name = "raze__tinyvec_macros__0_1_1",
        url = "https://crates.io/api/v1/crates/tinyvec_macros/0.1.1/download",
        type = "tar.gz",
        sha256 = "1f3ccbac311fea05f86f61904b462b55fb3df8837a366dfc601a0161d0532f20",
        strip_prefix = "tinyvec_macros-0.1.1",
        build_file = Label("//cargo/remote:BUILD.tinyvec_macros-0.1.1.bazel"),
    )

    maybe(
        http_archive,
        name = "raze__unicode_bidi__0_3_13",
        url = "https://crates.io/api/v1/crates/unicode-bidi/0.3.13/download",
        type = "tar.gz",
        sha256 = "92888ba5573ff080736b3648696b70cafad7d250551175acbaa4e0385b3e1460",
        strip_prefix = "unicode-bidi-0.3.13",
        build_file = Label("//cargo/remote:BUILD.unicode-bidi-0.3.13.bazel"),
    )

    maybe(
        http_archive,
        name = "raze__unicode_normalization__0_1_22",
        url = "https://crates.io/api/v1/crates/unicode-normalization/0.1.22/download",
        type = "tar.gz",
        sha256 = "5c5713f0fc4b5db668a2ac63cdb7bb4469d8c9fed047b1d0292cc7b0ce2ba921",
        strip_prefix = "unicode-normalization-0.1.22",
        build_file = Label("//cargo/remote:BUILD.unicode-normalization-0.1.22.bazel"),
    )

    maybe(
        http_archive,
        name = "raze__url__2_4_0",
        url = "https://crates.io/api/v1/crates/url/2.4.0/download",
        type = "tar.gz",
        sha256 = "50bff7831e19200a85b17131d085c25d7811bc4e186efdaf54bbd132994a88cb",
        strip_prefix = "url-2.4.0",
        build_file = Label("//cargo/remote:BUILD.url-2.4.0.bazel"),
    )
