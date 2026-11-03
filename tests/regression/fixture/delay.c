__attribute__((visibility("default"),noinline)) int delayed_answer(void){return 42;}
__attribute__((visibility("default"))) int delayed_value = 17;
static int constructor_value;
__attribute__((constructor)) static void initialize(void){
 int (*volatile answer)(void) = delayed_answer;
 constructor_value = answer();
}
__attribute__((visibility("default"))) int delayed_constructor_value(void){return constructor_value;}
