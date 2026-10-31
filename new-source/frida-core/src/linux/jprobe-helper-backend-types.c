#include "jprobe-helper-backend.h"
#include "helpers/inject-context.h"

G_STATIC_ASSERT (sizeof (JprobeHelperBootstrapContext) == sizeof (JprobeBootstrapContext));
G_STATIC_ASSERT (sizeof (JprobeHelperLoaderContext) == sizeof (JprobeLoaderContext));
G_STATIC_ASSERT (sizeof (JprobeHelperLibcApi) == sizeof (JprobeLibcApi));
G_STATIC_ASSERT (sizeof (JprobeHelperByeMessage) == sizeof (JprobeByeMessage));
