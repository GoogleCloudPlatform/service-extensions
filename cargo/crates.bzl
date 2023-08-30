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
        name = "raze__ahash__0_8_3",
        url = "https://crates.io/api/v1/crates/ahash/0.8.3/download",
        type = "tar.gz",
        sha256 = "2c99f64d1e06488f620f932677e24bc6e2897582980441ae90a671415bd7ec2f",
        strip_prefix = "ahash-0.8.3",
        build_file = Label("//cargo/remote:BUILD.ahash-0.8.3.bazel"),
    )

    maybe(
        http_archive,
        name = "raze__aho_corasick__1_0_5",
        url = "https://crates.io/api/v1/crates/aho-corasick/1.0.5/download",
        type = "tar.gz",
        sha256 = "0c378d78423fdad8089616f827526ee33c19f2fddbd5de1629152c9593ba4783",
        strip_prefix = "aho-corasick-1.0.5",
        build_file = Label("//cargo/remote:BUILD.aho-corasick-1.0.5.bazel"),
    )

    maybe(
        http_archive,
        name = "raze__cfg_if__1_0_0",
        url = "https://crates.io/api/v1/crates/cfg-if/1.0.0/download",
        type = "tar.gz",
        sha256 = "baf1de4339761588bc0619e3cbc0120ee582ebb74b53b4efbf79117bd2da40fd",
        strip_prefix = "cfg-if-1.0.0",
        build_file = Label("//cargo/remote:BUILD.cfg-if-1.0.0.bazel"),
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
        name = "raze__hashbrown__0_13_2",
        url = "https://crates.io/api/v1/crates/hashbrown/0.13.2/download",
        type = "tar.gz",
        sha256 = "43a3c133739dddd0d2990f9a4bdf8eb4b21ef50e4851ca85ab661199821d510e",
        strip_prefix = "hashbrown-0.13.2",
        build_file = Label("//cargo/remote:BUILD.hashbrown-0.13.2.bazel"),
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
        name = "raze__log__0_4_20",
        url = "https://crates.io/api/v1/crates/log/0.4.20/download",
        type = "tar.gz",
        sha256 = "b5e6163cb8c49088c2c36f57875e58ccd8c87c7427f7fbd50ea6710b2f3f2e8f",
        strip_prefix = "log-0.4.20",
        build_file = Label("//cargo/remote:BUILD.log-0.4.20.bazel"),
    )

    maybe(
        http_archive,
<<<<<<< HEAD
        name = "raze__memchr__2_6_3",
        url = "https://crates.io/api/v1/crates/memchr/2.6.3/download",
        type = "tar.gz",
        sha256 = "8f232d6ef707e1956a43342693d2a31e72989554d58299d7a88738cc95b0d35c",
        strip_prefix = "memchr-2.6.3",
        build_file = Label("//cargo/remote:BUILD.memchr-2.6.3.bazel"),
=======
        name = "raze__memchr__2_6_1",
        url = "https://crates.io/api/v1/crates/memchr/2.6.1/download",
        type = "tar.gz",
        sha256 = "f478948fd84d9f8e86967bf432640e46adfb5a4bd4f14ef7e864ab38220534ae",
        strip_prefix = "memchr-2.6.1",
        build_file = Label("//cargo/remote:BUILD.memchr-2.6.1.bazel"),
>>>>>>> 2c53118 (Include corresponding Cargo generated changes.)
    )

    maybe(
        http_archive,
        name = "raze__once_cell__1_18_0",
        url = "https://crates.io/api/v1/crates/once_cell/1.18.0/download",
        type = "tar.gz",
        sha256 = "dd8b5dd2ae5ed71462c540258bedcb51965123ad7e7ccf4b9a8cafaa4a63576d",
        strip_prefix = "once_cell-1.18.0",
        build_file = Label("//cargo/remote:BUILD.once_cell-1.18.0.bazel"),
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
        name = "raze__proxy_wasm__0_2_1",
        url = "https://crates.io/api/v1/crates/proxy-wasm/0.2.1/download",
        type = "tar.gz",
        sha256 = "823b744520cd4a54ba7ebacbffe4562e839d6dcd8f89209f96a1ace4f5229cd4",
        strip_prefix = "proxy-wasm-0.2.1",
        build_file = Label("//cargo/remote:BUILD.proxy-wasm-0.2.1.bazel"),
    )

    maybe(
        http_archive,
<<<<<<< HEAD
        name = "raze__regex__1_9_5",
        url = "https://crates.io/api/v1/crates/regex/1.9.5/download",
        type = "tar.gz",
        sha256 = "697061221ea1b4a94a624f67d0ae2bfe4e22b8a17b6a192afb11046542cc8c47",
        strip_prefix = "regex-1.9.5",
        build_file = Label("//cargo/remote:BUILD.regex-1.9.5.bazel"),
=======
        name = "raze__regex__1_9_4",
        url = "https://crates.io/api/v1/crates/regex/1.9.4/download",
        type = "tar.gz",
        sha256 = "12de2eff854e5fa4b1295edd650e227e9d8fb0c9e90b12e7f36d6a6811791a29",
        strip_prefix = "regex-1.9.4",
        build_file = Label("//cargo/remote:BUILD.regex-1.9.4.bazel"),
>>>>>>> 2c53118 (Include corresponding Cargo generated changes.)
    )

    maybe(
        http_archive,
<<<<<<< HEAD
        name = "raze__regex_automata__0_3_8",
        url = "https://crates.io/api/v1/crates/regex-automata/0.3.8/download",
        type = "tar.gz",
        sha256 = "c2f401f4955220693b56f8ec66ee9c78abffd8d1c4f23dc41a23839eb88f0795",
        strip_prefix = "regex-automata-0.3.8",
        build_file = Label("//cargo/remote:BUILD.regex-automata-0.3.8.bazel"),
=======
        name = "raze__regex_automata__0_3_7",
        url = "https://crates.io/api/v1/crates/regex-automata/0.3.7/download",
        type = "tar.gz",
        sha256 = "49530408a136e16e5b486e883fbb6ba058e8e4e8ae6621a77b048b314336e629",
        strip_prefix = "regex-automata-0.3.7",
        build_file = Label("//cargo/remote:BUILD.regex-automata-0.3.7.bazel"),
>>>>>>> 2c53118 (Include corresponding Cargo generated changes.)
    )

    maybe(
        http_archive,
        name = "raze__regex_syntax__0_7_5",
        url = "https://crates.io/api/v1/crates/regex-syntax/0.7.5/download",
        type = "tar.gz",
        sha256 = "dbb5fb1acd8a1a18b3dd5be62d25485eb770e05afb408a9627d14d451bae12da",
        strip_prefix = "regex-syntax-0.7.5",
        build_file = Label("//cargo/remote:BUILD.regex-syntax-0.7.5.bazel"),
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
        name = "raze__url__2_4_1",
        url = "https://crates.io/api/v1/crates/url/2.4.1/download",
        type = "tar.gz",
        sha256 = "143b538f18257fac9cad154828a57c6bf5157e1aa604d4816b5995bf6de87ae5",
        strip_prefix = "url-2.4.1",
        build_file = Label("//cargo/remote:BUILD.url-2.4.1.bazel"),
    )

    maybe(
        http_archive,
        name = "raze__version_check__0_9_4",
        url = "https://crates.io/api/v1/crates/version_check/0.9.4/download",
        type = "tar.gz",
        sha256 = "49874b5167b65d7193b8aba1567f5c7d93d001cafc34600cee003eda787e483f",
        strip_prefix = "version_check-0.9.4",
        build_file = Label("//cargo/remote:BUILD.version_check-0.9.4.bazel"),
    )
