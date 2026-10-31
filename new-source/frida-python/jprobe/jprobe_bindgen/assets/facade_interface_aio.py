class _Implementation:
    _loop: Any

    def _jprobe_dispatch(self, name: str, args: List[Any], completion: Any) -> None:
        loop = self._loop

        async def run() -> None:
            try:
                result = getattr(self, name)(*[_wrap(a) for a in args])
                if asyncio.iscoroutine(result):
                    result = await result
                result = _unwrap(result)
                error = None
            except Exception as e:
                result = None
                error = e
            _jprobe._complete_request(completion, result, error)

        _dispatch(loop, lambda: loop.create_task(run()))
