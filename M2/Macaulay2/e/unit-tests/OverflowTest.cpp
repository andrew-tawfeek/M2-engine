#include "monomials/overflow.hpp"

#include <gtest/gtest.h>

#include <cstdint>

#include "exceptions.hpp"

TEST(OverflowTest, Throw)
{
  // The common overflow path exposes the documented exception type.
  EXPECT_THROW(safe::ov("throw overflow exception"), exc::overflow_exception);
}

TEST(OverflowTest, SubOverflow)
{
  // Subtracting one from the smallest signed integer must not wrap.
  volatile int minimum = INT32_MIN;
  EXPECT_THROW(safe::sub(minimum, 1), exc::overflow_exception);
}

TEST(OverflowTest, AddOverflow)
{
  // Adding one to the largest signed integer must not wrap.
  volatile int maximum = INT32_MAX;
  EXPECT_THROW(safe::add(maximum, 1), exc::overflow_exception);
}

TEST(OverflowTest, MultOverflow)
{
  // The positive product 2^31 does not fit a signed 32-bit integer.
  volatile int factor = 0x8000;
  EXPECT_THROW(safe::mult(factor, 0x10000), exc::overflow_exception);
}

TEST(OverflowTest, DivOverflow)
{
  // Negating the minimum value through division is the signed division overflow
  // case.
  volatile int minimum = INT32_MIN;
  EXPECT_THROW(safe::div(minimum, -1), exc::overflow_exception);
}

TEST(OverflowTest, MinusOverflow)
{
  // Unary negation must reject the minimum value without overflowing in test
  // setup.
  volatile int minimum = INT32_MIN;
  EXPECT_THROW(safe::minus(minimum), exc::overflow_exception);
}
