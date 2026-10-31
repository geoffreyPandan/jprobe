static PyObject *
PyJprobe_get_device_manager (PyObject * module,
                            PyObject * args)
{
  static PyObject * manager = NULL;

  if (manager == NULL)
    manager = PyObject_CallFunction ((PyObject *) PYJPROBE_TYPE_OBJECT (DeviceManager), NULL);

  Py_IncRef (manager);

  return manager;
}
