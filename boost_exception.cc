#include <boost/throw_exception.hpp>

// NOTE: Ideally we would undefine BOOST_NO_EXCEPTIONS so we don't have to
// implement custom handlers here. I can't make it work. It's probably because
// boost Bazel targets are defined by rules_boost, and those their copts cannot
// be overridden by copts for the cc_binary:
// https://github.com/emscripten-core/emsdk/issues/972

namespace boost {

void throw_exception(std::exception const& e) { exit(1); }
void throw_exception(std::exception const& e,
                     boost::source_location const& loc) {
  exit(1);
}

}  // namespace boost
