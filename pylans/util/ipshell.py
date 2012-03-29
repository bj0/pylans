def _12shell(vars, message, prompt, exit_msg):
    #prompt_message = "Welcome!  Useful: G is the graph, DB, C"
    prompt_message = message

    from IPython.frontend.terminal.embed import InteractiveShellEmbed
    from IPython.config.loader import Config
    cfg = Config()
#        cfg.InteractiveShellEmbed.prompt_in1="pylans:ipy> "
    cfg.PromptManager.in_template="myprompt:> "
#        cfg.InteractiveShellEmbed.prompt_out="myprompt [\\#]: "
    cfg.InteractiveShellEmbed.profile="pysh"
    
    ipshell = InteractiveShellEmbed.instance(config=cfg, user_ns=vars,
                                    banner2=message, exit_msg=exit_msg)

    return  ipshell
    
        
def _10shell(vars, message, prompt, exit_msg):
    #prompt_message = "Welcome!  Useful: G is the graph, DB, C"
    prompt_message = message

    from IPython.Shell import IPShellEmbed
    ipshell = IPShellEmbed(argv=['-pi1','pylans:\\#>','-p','sh'],
        banner=prompt_message, exit_msg="Goodbye")
    return  ipshell


def shell(vars, message="Entering Interactive Python Interpreter",
            prompt="(py)pylans:>", exit_msg="Returning to pylans cli"):
    '''
        Start an interactive (i)python interpreter on the commandline.
        This blocks, so don't call from twisted, but in a thread or from Cmd is fine.
        
        :param vars: variables to make available to interpreter
        :type vars: dict
    '''
    try:
        import IPython
        version = IPython.__version__

        if version.startswith('0.10'):
            return _10shell(vars, message, prompt, exit_msg)
            
        elif version.startswith('0.11') or \
             version.startswith('0.12'):
             return _12shell(vars, message, prompt, exit_msg)

        else:
            raise ImportError('unknown IPython version: {0}'.format(version))

    except (ImportError, AttributeError):
        logger.error('could not find a compatible version of IPython', exc_info=True)
        ## this doesn't quite work right, in that it doesn't go to the right env
        ## so we just fail.
        import code
        import rlcompleter
        import readline
        readline.parse_and_bind("tab: complete")
        # calling this with globals ensures we can see the environment
        print message
        shell = code.InteractiveConsole(vars)
        return shell.interact
        
if __name__ == '__main__':
    p = shell(locals())
    p()

